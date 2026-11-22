# Phát kết quả qua Downstream.push và xử lý tín hiệu từ chối

Trong chương **Xây dựng Gatherer tùy biến** của **Java Stream API**, `Gatherer` mở rộng mô hình xử lý dữ liệu khai báo vượt ra ngoài những thao tác `filter`, `map`, `flatMap`, `reduce` và `collect` quen thuộc. Một gatherer có thể phát **không, một hoặc nhiều phần tử kết quả** cho mỗi phần tử đầu vào, duy trì trạng thái giữa những lần nhận dữ liệu và chủ động kết thúc quá trình nhận nguồn.

Điểm then chốt của bài này là **`Gatherer.Downstream.push(result)`**. Khi một gatherer muốn chuyển kết quả sang bước kế tiếp của pipeline, nó gọi `push` và nhận lại tín hiệu `boolean` cho biết downstream **còn muốn nhận thêm phần tử nữa hay không**. Tín hiệu này phải được xử lý đúng, đặc biệt khi downstream có `limit`, `findFirst`, `takeWhile` hoặc một gatherer khác có thể dừng sớm.

Nếu bỏ qua tín hiệu từ chối, gatherer có thể tiếp tục tạo kết quả vô ích hoặc tiêu thụ đầu vào không cần thiết. Nếu hiểu nhầm `false` là "phần tử vừa phát không được nhận", chương trình có thể bù thêm phần tử, tạo kết quả thừa hoặc vi phạm hợp đồng kết thúc. Bài học xây từ ví dụ nhỏ đến gatherer phát nhiều phần tử, đóng gói bộ đệm, xử lý `finisher` và lựa chọn integrator phù hợp.

> **Yêu cầu JDK:** Stream Gatherers là API chính thức từ **Java 24** (JEP 485); từng xuất hiện dưới dạng preview ở Java 22 và 23. Ví dụ hoàn chỉnh trong bài nhắm **JDK 24+**, không có trong Java 8, 11, 17 hoặc 21 tiêu chuẩn. Chạy ví dụ trên JDK 24+ không cần bật preview.

## 1. Vị trí của Downstream trong một gatherer

Một pipeline có thể trông như sau:

~~~java
List<Integer> result = Stream.of(1, 2, 3)
        .gather(myGatherer())
        .limit(3)
        .toList();
~~~

Nếu `myGatherer()` phát ra hai kết quả cho mỗi phần tử nhận vào, kết quả cuối có thể được giới hạn ở ba phần tử. Gatherer cần biết khi nào **bước phía sau không cần thêm kết quả**.

Sơ đồ luồng dữ liệu:

~~~text
Nguồn Stream<T>
      |
      v
  Gatherer<T, A, R>
      |
      +-- initializer(): tạo state A (nếu cần)
      |
      +-- integrator(state, T, downstream)
      |        |
      |        +---- downstream.push(R)
      |                    |
      |                    v
      |             Bước tiếp theo
      |           (limit / map / collect ...)
      |                    |
      |               boolean
      |              /       \
      |            true      false
      |        nhận tiếp    không nhận thêm
      |
      +-- finisher(state, downstream) (nếu có)
~~~

Bốn thành phần tạo nên hợp đồng tổng quát của `Gatherer<T, A, R>`:

| Thành phần | Chức năng | Có bắt buộc tự viết không? |
| --- | --- | --- |
| `initializer` | Tạo trạng thái tích lũy `A` | Không, gatherer không trạng thái có thể dùng dạng tiện ích |
| `integrator` | Xử lý một phần tử `T`; tùy ý đẩy ra các kết quả `R` | Có, là logic xử lý trung tâm |
| `combiner` | Gộp trạng thái khi triển khai song song | Không; gatherer tuần tự có thể không hỗ trợ gộp |
| `finisher` | Xử lý dữ liệu còn lại khi kết thúc nguồn | Không; chỉ dùng khi cần phát kết quả cuối hoặc dọn logic trạng thái |

`Downstream<? super R>` là đối tượng đại diện cho **bước kế tiếp trong pipeline**, chứ không phải một `List` hay `Consumer` do ứng dụng tự tạo. Gatherer có thể gọi `push` nhiều lần trong một invocation của integrator, hoặc không gọi lần nào.

## 2. Hợp đồng chính xác của Downstream.push

Trong Java 24, giao diện `Gatherer.Downstream<T>` có hai thao tác liên quan:

~~~java
boolean push(T element);

default boolean isRejecting();
~~~

Ý nghĩa của `push(element)`:

- Gatherer **đề xuất chuyển phần tử `element`** cho downstream.
- Nếu kết quả là `true`, downstream **vẫn có thể nhận thêm** kết quả.
- Nếu kết quả là `false`, downstream **không muốn nhận thêm kết quả**; các lần gọi `push` tiếp theo trên cùng downstream sẽ tiếp tục trả `false`.
- **Không suy ra phần tử vừa truyền bị loại** chỉ vì `push` trả `false`. Downstream có thể đã nhận phần tử đó rồi, và chính phần tử vừa nhận là phần tử cuối đáp ứng một giới hạn.
- Khi đã nhận `false`, gatherer nên **ngừng tạo/push thêm phần tử**, đồng thời truyền tín hiệu dừng ngược về upstream nếu không còn việc gì cần nhận thêm.

Ví dụ với `limit(3)`: downstream có thể nhận phần tử thứ ba, sau đó báo `false` vì đã đủ ba phần tử. Nếu gatherer cho rằng phần tử thứ ba chưa được gửi rồi cố gửi lại, nó đang diễn giải tín hiệu sai.

| Kết quả của `push(value)` | Cách hiểu | Hướng xử lý thông thường |
| --- | --- | --- |
| `true` | Vẫn có thể chuyển **thêm** kết quả | Tiếp tục logic nếu còn đầu ra hoặc đầu vào |
| `false` | Downstream không cần thêm kết quả | Dừng phát thêm, báo ngược rằng không cần tiếp tục |
| `false` ở lần push đầu | Downstream không cần nhận thêm sau lần này | Không tự suy rằng giá trị đầu đã bị mất |
| Tiếp tục gọi sau `false` | Các lời gọi sau vẫn trả `false` | Tránh vì chỉ gây công việc thừa |

Điểm tinh tế: `push` không phải giao thức "xác nhận ghi thành công vào cơ sở dữ liệu" hay "phần tử vừa gửi chắc chắn tồn tại trong một danh sách". Nó là **tín hiệu nhu cầu tiếp nhận tiếp theo** của pipeline. Nếu bước sau là một filter, có thể phần tử được xét rồi bị lọc; nếu là `limit`, phần tử vừa được xét có thể là phần tử cuối.

## 3. Boolean của integrator khác boolean của push

Integrator có hợp đồng:

~~~java
boolean integrate(
        A state,
        T element,
        Gatherer.Downstream<? super R> downstream);
~~~

Boolean mà **integrator trả về cho runtime** có ý nghĩa:

- `true`: integrator còn muốn nhận phần tử **đầu vào tiếp theo**.
- `false`: integrator muốn **ngừng nhận đầu vào tiếp theo**; thao tác gather có thể kết thúc sớm.

Hai tín hiệu thường liên quan nhưng không đồng nhất:

~~~text
downstream.push(output) -> false
       |
       v
Integrator nên return false
       |
       v
Runtime dừng cung cấp đầu vào mới cho gatherer
~~~

Tuy nhiên, integrator còn có thể **chủ động return false** vì chính điều kiện nghiệp vụ của nó, ngay cả khi downstream chưa từ chối. Ví dụ gatherer tự dừng sau khi gặp một mốc hoặc sau khi đã phát đủ `N` phần tử.

Trường hợp không phát phần tử:

~~~java
if (!shouldEmit(element)) {
    return true; // Bỏ một đầu ra nhưng vẫn nhận đầu vào tiếp theo.
}
~~~

Trường hợp phát một phần tử và không có chính sách dừng riêng:

~~~java
return downstream.push(transform(element));
~~~

Đây là cách truyền thẳng tín hiệu nhu cầu từ downstream tới upstream. **Không tự động dùng `return false` chỉ vì không phát kết quả**: như thế sẽ dừng cả nguồn thay vì chỉ lọc một phần tử.

## 4. Ví dụ nhỏ: phát một giá trị và chuyển tiếp tín hiệu

Một gatherer không có trạng thái có thể được tạo bằng `Gatherer.ofSequential`:

~~~java
import java.util.stream.Gatherer;

static Gatherer<Integer, Void, Integer> plusOne() {
    return Gatherer.<Integer, Integer>ofSequential(
            Gatherer.Integrator.of(
                    (unused, value, downstream) ->
                            downstream.push(value + 1)
            )
    );
}
~~~

Ý nghĩa kiểu:

- Đầu vào `T = Integer`.
- Không cần state nghiệp vụ nên kiểu trạng thái `A = Void`.
- Đầu ra `R = Integer`.
- `ofSequential` chọn gatherer xử lý theo chế độ tuần tự phù hợp với bài minh họa.
- `Integrator.of(...)` tạo integrator có thể truyền tín hiệu dừng.

Dùng:

~~~java
List<Integer> values = Stream.of(1, 2, 3)
        .gather(plusOne())
        .toList();

// [2, 3, 4]
~~~

Nếu downstream giới hạn đầu ra:

~~~java
List<Integer> values = Stream.of(1, 2, 3)
        .gather(plusOne())
        .limit(1)
        .toList();

// [2]
~~~

Sau khi giá trị `2` được đẩy xuống và `limit(1)` đã có đủ kết quả, `push` có thể trả `false`; integrator chuyển `false` trở lại runtime để ngừng lấy thêm nguồn. Không nên thêm side effect vào `plusOne` rồi khẳng định mọi phần tử của Stream nguồn chắc chắn đã được xử lý.

## 5. Phát nhiều kết quả: phải kiểm tra sau mỗi push

Ví dụ mỗi số nguyên sinh hai kết quả: chính số đó và số nhân mười.

~~~java
static Gatherer<Integer, Void, Integer> expand() {
    return Gatherer.<Integer, Integer>ofSequential(
            Gatherer.Integrator.of(
                    (unused, value, downstream) -> {
                        if (!downstream.push(value)) {
                            return false;
                        }
                        return downstream.push(value * 10);
                    }
            )
    );
}
~~~

Với nguồn `[1, 2, 3]`:

~~~java
List<Integer> expanded = Stream.of(1, 2, 3)
        .gather(expand())
        .toList();

System.out.println(expanded);
// [1, 10, 2, 20, 3, 30]
~~~

Khi thêm `limit(3)`:

~~~java
List<Integer> firstThree = Stream.of(1, 2, 3)
        .gather(expand())
        .limit(3)
        .toList();

System.out.println(firstThree);
// [1, 10, 2]
~~~

Trình tự logic trong thực thi tuần tự:

~~~text
Input 1:
  push(1)   -> downstream còn muốn nhận thêm
  push(10)  -> downstream còn muốn nhận thêm

Input 2:
  push(2)   -> downstream đủ 3 kết quả; có thể trả false
  KHÔNG push(20)
  KHÔNG cần lấy thêm input 3
~~~

**Không nên viết**:

~~~java
// Sai về giao thức từ chối: vẫn cố phát tiếp sau khi bị từ chối.
downstream.push(value);
downstream.push(value * 10);
return true;
~~~

Với downstream từ chối sớm, kết quả cuối có thể vẫn trông "đúng" do các `push` sau bị bỏ qua, nhưng gatherer đã làm thêm công việc không cần thiết và tiếp tục nhận đầu vào mà không có lý do. Nếu sinh kết quả liên quan đến I/O hoặc tính toán nặng, chi phí này đáng kể.

Dùng mẫu:

~~~java
if (!downstream.push(firstOutput)) {
    return false;
}

return downstream.push(secondOutput);
~~~

Nếu có `N` đầu ra trong một vòng lặp, kiểm tra kết quả của **mỗi** `push` rồi thoát ngay khi gặp `false`.

## 6. Ví dụ hoàn chỉnh chạy trên Java 24+: phát nhiều, dừng downstream và dừng chủ động

Chương trình `DownstreamPushDemo.java` dưới đây minh họa hai khả năng: downstream từ chối qua `limit` và gatherer tự dừng sau khi phát đủ số phần tử theo cấu hình.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class DownstreamPushDemo {

    static Gatherer<Integer, Void, Integer> expand() {
        return Gatherer.<Integer, Integer>ofSequential(
                Gatherer.Integrator.of(
                        (unused, number, downstream) -> {
                            if (!downstream.push(number)) {
                                return false;
                            }
                            return downstream.push(number * 10);
                        }
                )
        );
    }

    static final class Counter {
        int emitted;
    }

    static Gatherer<Integer, Counter, Integer> takeAtMost(int max) {
        if (max < 0) {
            throw new IllegalArgumentException(
                    "max must be non-negative");
        }

        return Gatherer.<Integer, Counter, Integer>ofSequential(
                Counter::new,
                Gatherer.Integrator.of(
                        (state, number, downstream) -> {
                            if (state.emitted >= max) {
                                return false;
                            }

                            state.emitted++;
                            boolean wantsMore = downstream.push(number);

                            // Dừng nếu chính Gatherer đạt giới hạn
                            // HOẶC downstream không cần thêm dữ liệu.
                            return wantsMore && state.emitted < max;
                        }
                )
        );
    }

    public static void main(String[] args) {
        List<Integer> all = Stream.of(1, 2, 3)
                .gather(expand())
                .toList();

        List<Integer> limitedDownstream = Stream.of(1, 2, 3)
                .gather(expand())
                .limit(3)
                .toList();

        List<Integer> limitedGatherer = Stream.of(1, 2, 3, 4)
                .gather(takeAtMost(2))
                .toList();

        System.out.println(all);
        System.out.println(limitedDownstream);
        System.out.println(limitedGatherer);
    }
}
~~~

Kết quả:

~~~text
[1, 10, 2, 20, 3, 30]
[1, 10, 2]
[1, 2]
~~~

Chạy trên JDK 24+:

~~~bash
javac --release 24 DownstreamPushDemo.java
java DownstreamPushDemo
~~~

Phân biệt hai tình huống trong mã:

- `limitedDownstream`: `expand` **không tự biết** giới hạn ba kết quả. Nó biết cần dừng khi `push` trả `false` do `limit(3)` phía sau.
- `limitedGatherer`: `takeAtMost(2)` **tự chủ động dừng** sau khi phát hai phần tử, cho dù downstream sẵn sàng nhận thêm.

**Lưu ý với `max == 0`:** gatherer `takeAtMost(0)` không phát gì nhưng có thể cần runtime đưa tới integrator một phần tử đầu vào để nó nhận ra phải trả `false`. Nếu yêu cầu là **không tiêu thụ bất kỳ phần tử upstream nào** khi giới hạn bằng 0, dùng `stream.limit(0)` hoặc thiết kế một nhánh trước khi bắt đầu pipeline; đừng khẳng định ví dụ gatherer này có thuộc tính zero-consumption.

## 7. Lọc phần tử: không push cũng không có nghĩa dừng

Gatherer có thể quyết định không phát gì với một đầu vào, tương tự `filter`. Khi bỏ qua một phần tử mà chưa có lý do dừng, integrator phải trả `true`.

~~~java
static Gatherer<Integer, Void, Integer> evenOnly() {
    return Gatherer.<Integer, Integer>ofSequential(
            Gatherer.Integrator.of(
                    (unused, number, downstream) -> {
                        if (number % 2 != 0) {
                            return true;
                        }
                        return downstream.push(number);
                    }
            )
    );
}
~~~

Dùng:

~~~java
List<Integer> evens = Stream.of(1, 2, 3, 4, 5, 6)
        .gather(evenOnly())
        .toList();

System.out.println(evens); // [2, 4, 6]
~~~

Nếu viết `return false` cho số lẻ đầu tiên, pipeline có thể dừng ngay khi gặp `1` và không bao giờ đến `2`, `4` hoặc `6`.

| Hành vi trong integrator | Giá trị trả về thường đúng |
| --- | --- |
| Bỏ qua phần tử hiện tại nhưng còn muốn đọc tiếp | `true` |
| Đẩy một phần tử; downstream vẫn nhận thêm | `true` từ `push` |
| Đẩy một phần tử; downstream từ chối thêm | `false` từ `push` |
| Đã đạt điều kiện kết thúc riêng của gatherer | `false` |
| Chưa có đầu ra nhưng chưa đạt điều kiện kết thúc | `true` |

**Quy tắc thiết kế:** Hãy hỏi "còn cần **phần tử nguồn tiếp theo** không?" để chọn boolean của integrator. Hãy hỏi "bước phía sau còn muốn **đầu ra tiếp theo** không?" để hiểu boolean của `push`.

## 8. Phân biệt Integrator.of và Integrator.ofGreedy

Java cung cấp:

~~~java
Gatherer.Integrator.of(integrator)

Gatherer.Integrator.ofGreedy(greedyIntegrator)
~~~

`Integrator.of` cho phép integrator **tự khởi tạo short-circuit** bằng cách trả `false`, kể cả khi downstream chưa từ chối.

`Integrator.ofGreedy` mô tả một integrator **không tự ý dừng đọc nguồn**. Nó có thể trả `false` để **chuyển tiếp sự từ chối của downstream**, nhưng không được tự dừng vì một điều kiện nghiệp vụ riêng. Thông tin này giúp implementation tối ưu hóa pipeline phù hợp.

Ví dụ integrator lọc giá trị trống nhưng vẫn duyệt đến hết nguồn (trừ khi downstream yêu cầu dừng):

~~~java
static Gatherer<String, Void, String> nonBlank() {
    return Gatherer.<String, String>ofSequential(
            Gatherer.Integrator.ofGreedy(
                    (unused, text, downstream) -> {
                        if (text.isBlank()) {
                            return true;
                        }
                        return downstream.push(text);
                    }
            )
    );
}
~~~

Đây là ví dụ dùng Java 24+ nên có thể sử dụng `String.isBlank()` (Java 11+).

Không dùng `ofGreedy` cho gatherer `takeAtMost` ở phần 6. Gatherer đó **có thể return false vì đã đạt giới hạn riêng**, ngay cả khi downstream còn sẵn sàng nhận, nên không phù hợp với lời cam kết "greedy".

Một lưu ý: "greedy" không có nghĩa **phải phát ít nhất một kết quả cho mỗi input**. Một integrator greedy có thể lọc bỏ phần tử, tích lũy trong bộ đệm hoặc phát nhiều phần tử; nó chỉ không tự khởi tạo việc ngừng lấy đầu vào.

## 9. isRejecting: khi nào cần và giới hạn bảo đảm

Bên cạnh `push`, downstream có phương thức:

~~~java
boolean isRejecting();
~~~

Nó cho biết downstream **được biết là đang từ chối** nhận thêm phần tử hay không. Đây là một cơ chế **best-effort**:

- Khi `isRejecting()` trả `true`, downstream đã được biết là không cần thêm dữ liệu.
- Khi trả `false`, **không nên suy ra chắc chắn** downstream sẽ nhận mọi lần `push` kế tiếp. Giao diện cho phép implementation mặc định luôn trả `false`.
- Trong xử lý bình thường, kết quả của `push` là nguồn thông tin trực tiếp cần kiểm tra.
- Một khi `push` đã trả `false`, các lần `push` sau trên cùng downstream cũng trả `false`; tránh làm những lần gọi dư thừa.

`isRejecting` đặc biệt hữu ích ở **finisher**, bởi vì finisher có thể được gọi sau khi quá trình tích lũy kết thúc mà downstream đã không cần thêm đầu ra.

Ví dụ:

~~~java
(state, downstream) -> {
    if (!state.pending.isEmpty() && !downstream.isRejecting()) {
        downstream.push(List.copyOf(state.pending));
    }
}
~~~

Mã này kiểm tra trước để tránh công việc phát còn sót **khi đã biết** downstream từ chối. Nhưng kết quả `false` của `isRejecting()` vẫn chỉ là tín hiệu best-effort; nếu có nhiều đầu ra trong finisher, phải kiểm tra kết quả `push` sau từng lần phát.

**Không dùng `isRejecting` làm điều kiện thay thế cho mọi `push`**, hoặc dùng nó như một khóa đồng bộ hóa giữa các luồng. Nó là cơ chế thông báo nhu cầu trong pipeline, không phải API điều phối thread.

## 10. Finisher phát phần còn lại: kiểm tra downstream trước khi đẩy

Gatherer có trạng thái thường tích lũy một phần dữ liệu rồi phát ra kết quả. Ví dụ, gom từng **hai** số thành một danh sách; khi nguồn hết mà còn một số lẻ, finisher phát nhóm cuối.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class BatchGathererDemo {

    static Gatherer<Integer, ArrayList<Integer>, List<Integer>>
    batchesOf(int size) {

        if (size <= 0) {
            throw new IllegalArgumentException("size must be positive");
        }

        return Gatherer.<Integer, ArrayList<Integer>, List<Integer>>
                ofSequential(
                    ArrayList::new,
                    Gatherer.Integrator.of(
                            (buffer, value, downstream) -> {
                                buffer.add(value);

                                if (buffer.size() < size) {
                                    return true;
                                }

                                // Sao chép trước khi xóa để không
                                // lộ buffer mutable ra ngoài.
                                List<Integer> batch = List.copyOf(buffer);
                                buffer.clear();

                                return downstream.push(batch);
                            }
                    ),
                    (buffer, downstream) -> {
                        // Có thể còn một nhóm chưa đủ size.
                        // Tránh phát nếu biết downstream từ chối.
                        if (!buffer.isEmpty() &&
                                !downstream.isRejecting()) {
                            downstream.push(List.copyOf(buffer));
                        }
                    }
                );
    }

    public static void main(String[] args) {
        List<List<Integer>> all = Stream.of(1, 2, 3, 4, 5)
                .gather(batchesOf(2))
                .toList();

        List<List<Integer>> onlyOne = Stream.of(1, 2, 3, 4, 5)
                .gather(batchesOf(2))
                .limit(1)
                .toList();

        System.out.println(all);     // [[1, 2], [3, 4], [5]]
        System.out.println(onlyOne); // [[1, 2]]
    }
}
~~~

Với danh sách năm phần tử, integrator phát hai nhóm đủ cỡ `[1,2]`, `[3,4]`, rồi finisher phát `[5]`. Kết quả không cần giữ toàn bộ nguồn, chỉ giữ bộ đệm tối đa `size` phần tử trong quá trình tích lũy.

Với `limit(1)`, downstream chỉ cần nhóm `[1,2]`. `push([1,2])` có thể trả `false`; integrator trả `false`, nguồn không cần được tiêu thụ tiếp cho gatherer. Nếu finisher được gọi sau một lượt xử lý đã dừng, nó không được cố phát thêm nhóm không cần thiết.

**Chi tiết kỹ thuật quan trọng:** `List.copyOf(buffer)` tạo danh sách đầu ra không sửa đổi được; nhờ đó lần `buffer.clear()` tiếp theo không làm thay đổi nhóm đã phát. Cách này chỉ chấp nhận các phần tử không `null`; ví dụ dùng `Integer` có giá trị hợp lệ.

Cách làm trên ưu tiên minh họa **giao thức downstream và quyền sở hữu buffer**. Nếu hệ thống cần chia batch song song hiệu quả theo cách vẫn giữ ranh giới encounter order, phải thiết kế thêm semantics của combiner và các quy tắc kết hợp trạng thái — không chỉ thay `ofSequential` bằng `of`.

## 11. Không giữ tham chiếu Downstream cho lần gọi sau

Một đối tượng `Gatherer.Downstream` chỉ có ý nghĩa trong **phạm vi lời gọi callback** mà implementation cung cấp. Không cất nó vào một trường để sử dụng trong thread khác, callback bất đồng bộ, task nền hoặc sau khi `integrate`/`finisher` đã trả về.

**Sai ý tưởng:**

~~~java
// Đừng làm thế này trong state của gatherer:
state.savedDownstream = downstream;

// ... hoặc gửi downstream vào một task khác rồi gọi push sau.
~~~

Lý do:

1. API không cấp quyền sở hữu lâu dài đối với downstream.
2. Runtime có thể thay đổi trạng thái xử lý và dừng pipeline sau khi callback kết thúc.
3. Việc giữ lại/downstream và truy cập từ luồng khác phá giả định quản lý phân vùng và kết hợp của Gatherer.
4. Tín hiệu từ chối có thể đã thay đổi; công việc phát ra muộn không còn hợp đồng hợp lệ.

Nếu cần xử lý bất đồng bộ, phải thiết kế một cơ chế queue, cancellation, lifecycle và điều phối riêng phù hợp với ứng dụng. Không biến `Gatherer.Downstream` thành một API push bất đồng bộ đa luồng tự do.

## 12. Một đầu vào tạo nhiều đầu ra: tránh lãng phí sau khi bị từ chối

Giả sử mỗi sự kiện cần tạo nhiều chuỗi kết quả:

~~~java
static Gatherer<String, Void, String> variants() {
    return Gatherer.<String, String>ofSequential(
            Gatherer.Integrator.of(
                    (unused, value, downstream) -> {
                        String normalized = value.trim();

                        if (!downstream.push(normalized)) {
                            return false;
                        }

                        String upper = normalized.toUpperCase(
                                java.util.Locale.ROOT);
                        return downstream.push(upper);
                    }
            )
    );
}
~~~

Điểm tối ưu ở đây không chỉ là tránh `push` thứ hai. Ta còn **không tính `upper` nếu downstream đã đủ kết quả sau `normalized`**. Khi tạo đầu ra tốn CPU, cấp phát nhiều object hoặc gọi một thao tác có chi phí cao, thứ tự này quan trọng.

Nếu không biết trước downstream cần bao nhiêu kết quả, đừng tạo một `List` chứa hàng nghìn biến thể trước rồi mới cố đẩy. Có thể sinh từng giá trị và kiểm tra `push` ngay, miễn việc sinh đó đúng hợp đồng và không dựa vào side effect bị bỏ dở.

Ví dụ mẫu khi mỗi phần tử có một collection các kết quả con:

~~~java
for (String candidate : candidates) {
    if (!downstream.push(candidate)) {
        return false;
    }
}
return true;
~~~

Với nguồn con từ I/O hoặc `Stream` có tài nguyên, phải đóng tài nguyên đó đúng phạm vi, kể cả khi gặp `push == false` và thoát sớm. `push` không tự đóng `Files.lines`, `Scanner` hay HTTP cursor được mở trong mã người dùng.

## 13. Phân biệt rejection, short-circuit và exception

Các tình huống sau không giống nhau:

| Tình huống | Tín hiệu / hành vi | Cách hiểu |
| --- | --- | --- |
| Downstream đã đủ đầu ra | `push(...) == false` | Không cần push thêm |
| Gatherer đạt ngưỡng riêng | `integrator returns false` | Không cần lấy input tiếp theo |
| Một đầu vào bị lọc | Không push; `integrator returns true` | Tiếp tục xử lý đầu vào khác |
| Mapper hoặc integrator ném exception | Pipeline thất bại | Cần báo lỗi và giải phóng tài nguyên theo vòng đời |
| Finisher còn dữ liệu khi downstream rejecting | `isRejecting()` có thể true | Không cố phát giá trị dư |
| Terminal hoàn tất bình thường | Kết quả được tạo xong | Không đồng nghĩa với việc Stream I/O tự đóng |

Một gatherer **không nên coi từ chối downstream là lỗi** và ném exception chỉ vì `push` trả `false`. Đó thường là **cơ chế kết thúc bình thường** khi pipeline đã có đủ dữ liệu.

Ngược lại, nếu một hàm biến đổi không thể xử lý dữ liệu vì lỗi nghiệp vụ, không được che lỗi bằng cách `return false`: caller sẽ hiểu pipeline **kết thúc bình thường**, có thể công bố kết quả thiếu dữ liệu. Hãy sử dụng cơ chế báo lỗi rõ ràng nếu đó là failure.

## 14. Hành vi với limit(0), findFirst, takeWhile và downstream lồng nhau

Một gatherer tùy biến không thể giả định terminal operation luôn duyệt toàn bộ nguồn.

### `limit(0)`

~~~java
List<Integer> none = Stream.of(1, 2, 3)
        .gather(expand())
        .limit(0)
        .toList();

// []
~~~

Downstream đã biết không cần đầu ra. Runtime có thể tối ưu để không gọi integrator; không được dựa vào callback `integrate` luôn chạy ít nhất một lần.

### `findFirst`

~~~java
int first = Stream.of(1, 2, 3)
        .gather(expand())
        .findFirst()
        .orElseThrow();

// 1
~~~

Khi kết quả đầu tiên đáp ứng yêu cầu, downstream không cần thêm. Gatherer không nên tạo đầu ra thứ hai hay đọc input sau chỉ để phục vụ một terminal operation đã hoàn tất.

### `takeWhile`

~~~java
List<Integer> prefix = Stream.of(1, 2, 3, 4)
        .gather(expand())
        .takeWhile(n -> n < 15)
        .toList();

// [1, 10, 2]
~~~

Dãy logic sau gatherer là `[1,10,2,20,3,30,4,40]`. `takeWhile(n -> n < 15)` dừng tại `20`, chỉ giữ `[1,10,2]`. Giá trị `20` **không nằm trong kết quả**, nhưng đã được đưa tới downstream để kiểm tra predicate. Đây là ví dụ vì sao `push(false)` **không nói lên phần tử vừa đẩy có thuộc kết quả hay không** — điều đó phụ thuộc bước downstream.

### Gatherer ghép tiếp gatherer

~~~java
List<Integer> result = Stream.of(1, 2, 3, 4)
        .gather(expand())
        .gather(takeAtMost(3))
        .toList();

// [1, 10, 2]
~~~

Tín hiệu dừng có thể truyền qua nhiều tầng: gatherer `takeAtMost(3)` ngừng nhận sau ba kết quả, khiến gatherer `expand` phía trước không phải sinh thêm. Không nên giả định mỗi gatherer hoạt động độc lập về nhu cầu tiêu thụ.

## 15. Song song hóa và tín hiệu từ chối: đừng hứa điều API không cam kết

Các ví dụ trong bài dùng `Gatherer.ofSequential` để mô tả hành vi rõ ràng trên nguồn có thứ tự. Khi nguồn gọi `parallel()`, tính đúng còn phụ thuộc kiểu gatherer và hợp đồng kết hợp trạng thái.

- Gatherer có `defaultCombiner()` được xử lý theo cơ chế tuần tự của Gatherer, **không trở thành song song hiệu quả** chỉ nhờ upstream `parallel()`.
- Muốn parallel hóa một gatherer có state, cần thiết kế `initializer` độc lập theo phân vùng và `combiner` đúng, đặc biệt khi kết quả phụ thuộc encounter order.
- Với gatherer có thể short-circuit, runtime phải quản lý các phân vùng và đầu ra theo hợp đồng Stream/Gatherer. **Không giả định số lượng callback, thứ tự callback hay tác dụng phụ tương đương một vòng lặp tuần tự**.
- `push == false` vẫn có nghĩa "downstream không muốn nhận thêm"; không được suy rằng mọi tác vụ upstream ở các phân vùng khác đã dừng tức thời.
- Lambda gọi `push` phải hoàn tất trong phạm vi invocation của nó; không giữ downstream để đẩy từ thread khác.
- Tránh side effect cần đúng một lần hoặc có giao dịch trong integrator; short-circuit và parallelism làm số lần thực hiện tác dụng phụ khó suy luận.

Trong thực tế, bắt đầu với gatherer tuần tự đúng hợp đồng, đo lường, rồi mới cân nhắc triển khai kết hợp song song. Một gatherer trả đúng `List` trên 10 phần tử không đủ chứng minh an toàn song song trên hàng triệu bản ghi.

## 16. Tài nguyên I/O và việc hủy sớm

Khi upstream đọc tệp bằng `Files.lines`, việc downstream từ chối sớm **không tự đóng nguồn**. Cần `try-with-resources`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<Integer> firstNumbers(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {

        return lines.map(Integer::parseInt)
                .gather(expand())
                .limit(3)
                .toList();
    }
}
~~~

Ở đây `expand()` là phương thức trong cùng lớp của ví dụ `DownstreamPushDemo`. Nếu đặt mã trong lớp khác, cần gọi đúng tên lớp hoặc truyền Gatherer từ bên ngoài.

`limit(3)` làm pipeline có thể dừng sớm, nhưng **`Files.lines` vẫn cần được đóng** khi ra khỏi khối `try`. Nếu `Integer.parseInt` ném `NumberFormatException`, `try-with-resources` vẫn gọi `close()` trước khi exception được truyền ra ngoài.

Nếu integrator mở tài nguyên riêng cho từng input, đừng đợi một callback `onClose` không chắc đã được gọi theo cách bạn mong muốn. Hãy quản lý từng nguồn trong phạm vi `try-with-resources` hoặc thiết kế quyền sở hữu tài nguyên rõ ràng. Từ chối downstream là cơ chế kết thúc **nhu cầu dữ liệu**, không phải một cơ chế đóng file/transaction.

## 17. Các lỗi thường gặp và cách sửa

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Pipeline vẫn xử lý nhiều input sau khi `limit` đã đủ | Integrator bỏ qua `push == false` và luôn `return true` | Trả ngay `false` khi downstream từ chối |
| Phát thừa giá trị thứ hai trong gatherer một-nhiều | Không kiểm tra kết quả của lần `push` đầu | Kiểm tra sau từng `push`, dùng early return |
| `return false` cho phần tử bị lọc | Nhầm "không phát" với "ngừng đọc nguồn" | Không push và `return true` |
| Mất phần tử cuối khi `push` trả `false` | Hiểu sai rằng phần tử vừa push chắc chắn bị từ chối | Không phát bù; boolean chỉ nói về việc nhận thêm |
| Phát thêm batch trong finisher sau khi đã đủ `limit` | Không kiểm tra trạng thái downstream | Dùng `isRejecting` best-effort, tránh phát khi biết rejecting |
| `isRejecting() == false` nhưng `push` vẫn trả `false` | `isRejecting` chỉ best-effort | Dựa vào kết quả `push` để quyết định dừng |
| `ofGreedy` chủ động dừng vì đạt ngưỡng | Vi phạm cam kết greedy | Dùng `Integrator.of` cho short-circuit riêng |
| Kết quả cũ bị thay đổi sau khi batch mới hình thành | Phát tham chiếu tới buffer mutable rồi `clear()` | Copy snapshot trước khi push |
| Thread khác gọi `push` sau khi callback đã kết thúc | Giữ Downstream trong state hoặc task bất đồng bộ | Chỉ dùng Downstream trong phạm vi callback |
| Một phần I/O bị giữ mở sau `findFirst` | Short-circuit không đồng nghĩa đóng nguồn | Dùng `try-with-resources` |
| Chuyển sang parallel khiến thứ tự/hiệu năng khó đoán | Thiếu thiết kế combiner và encounter order | Bắt đầu `ofSequential`; thiết kế song song riêng nếu cần |
| Báo lỗi bằng `return false` | Lẫn lộn kết thúc bình thường với lỗi nghiệp vụ | Ném/ghi nhận lỗi đúng cơ chế của ứng dụng |

## 18. Chiến lược kiểm thử gatherer

Một bộ kiểm thử tốt phải kiểm tra cả **giá trị đầu ra** lẫn **hành vi ngừng phát/ngừng tiêu thụ**:

1. **Nguồn rỗng:** không phát kết quả khi không có input; finisher chỉ phát nếu có dữ liệu cần hoàn tất.
2. **Một input → một output:** `push` được chuyển tiếp đúng.
3. **Một input → nhiều output:** giữ thứ tự kết quả trong pipeline tuần tự có encounter order.
4. **Một input → không output:** không vô tình dừng toàn bộ nguồn.
5. **`limit(0)`, `limit(1)`, `limit(k)`:** không phát quá số lượng downstream cần.
6. **`findFirst`, `takeWhile`:** đúng phần tử đầu/tiền tố, không sinh thêm kết quả vô ích sau khi biết từ chối.
7. **Gatherer tự dừng:** ngừng sau điều kiện riêng mà không cần chờ downstream từ chối.
8. **Finisher có buffer:** phát phần còn lại khi thích hợp, không phát dư khi downstream đã đủ dữ liệu.
9. **Input có lỗi hoặc I/O:** exception không bị chuyển thành thành công giả, nguồn được đóng.
10. **Trạng thái/parallel:** không chia sẻ state mutable hoặc giữ downstream vượt quá phạm vi callback.

Ví dụ những phép kiểm tra đơn giản trên JDK 24+:

~~~java
List<Integer> all = Stream.of(1, 2, 3)
        .gather(expand())
        .toList();

List<Integer> limited = Stream.of(1, 2, 3)
        .gather(expand())
        .limit(3)
        .toList();

List<Integer> first = Stream.of(1, 2, 3)
        .gather(expand())
        .limit(1)
        .toList();

if (!all.equals(List.of(1, 10, 2, 20, 3, 30))
        || !limited.equals(List.of(1, 10, 2))
        || !first.equals(List.of(1))) {
    throw new AssertionError("Incorrect gatherer output");
}
~~~

Những kiểm tra này giúp phát hiện sai nội dung, nhưng **không tự chứng minh** gatherer không tạo công việc thừa bên trong. Để xem xét hiệu năng, dùng một mapper tính toán có bộ đếm **chỉ trong môi trường kiểm thử**, hoặc mô phỏng downstream từ chối theo hợp đồng. Không biến side effect quan sát được thành thành phần của logic sản xuất.

## 19. Bài tập thực hành

### Bài 1 — Dự đoán output và tín hiệu từ chối

~~~java
List<Integer> result = Stream.of(3, 4)
        .gather(expand())
        .limit(3)
        .toList();
~~~

**Đáp án:** `[3, 30, 4]`. Khi đã nhận ba kết quả, downstream không cần thêm; `push(4)` có thể trả `false`, nên gatherer không cần `push(40)`.

### Bài 2 — Vì sao trả false cho phần tử bị lọc là sai?

~~~java
if (number % 2 != 0) {
    return false;
}
return downstream.push(number);
~~~

**Đáp án:** `false` của integrator nghĩa là **ngừng đọc input tiếp theo**, không phải "bỏ qua phần tử". Với nguồn bắt đầu bằng `1`, gatherer có thể dừng trước `2`, `4` và `6`. Cần `return true` khi bỏ một phần tử nhưng vẫn muốn xử lý nguồn.

### Bài 3 — Downstream.push trả false có nghĩa giá trị vừa push bị mất?

**Đáp án:** Không. Ví dụ `limit(1)` có thể nhận chính giá trị vừa đẩy rồi trả `false` vì đã đủ. Tùy bước downstream, phần tử vừa xử lý có thể được giữ hoặc bị filter/takeWhile loại; boolean chỉ biểu thị **nhu cầu thêm dữ liệu**.

### Bài 4 — Chọn Integrator.of hay ofGreedy?

Một gatherer đọc các số cho đến khi gặp số âm đầu tiên, sau đó tự dừng dù downstream còn nhận thêm. Dùng gì?

**Đáp án:** Dùng `Integrator.of`. Nó cho phép integrator tự trả `false` vì điều kiện kết thúc riêng. `ofGreedy` chỉ thích hợp khi integrator không tự khởi tạo short-circuit.

### Bài 5 — Vì sao phải copy buffer trước khi push?

~~~java
downstream.push(buffer);
buffer.clear();
~~~

**Đáp án:** Nếu `buffer` là `ArrayList` mutable, downstream có thể giữ tham chiếu đến chính object đó, và `clear()` khiến kết quả đã gửi trở thành danh sách rỗng. Dùng `List.copyOf(buffer)` hoặc bản sao riêng trước khi xóa để tránh thay đổi output đã phát.

### Bài 6 — Dùng isRejecting khi nào?

Một finisher giữ phần tử cuối còn sót, nhưng downstream đã đủ `limit(1)`. Có nên cố đẩy phần tử cuối không?

**Đáp án:** Không. Có thể kiểm tra `downstream.isRejecting()` để tránh đẩy khi đã biết downstream từ chối. Nhưng `isRejecting() == false` không chứng minh chắc chắn downstream còn cần dữ liệu; nếu phát nhiều phần tử, cần kiểm tra kết quả từng `push`.

### Bài 7 — Tương thích JDK

Một dự án có runtime **Java 21** muốn dùng `Stream.gather` chính thức mà không có preview. Có biên dịch/chạy trực tiếp được không?

**Đáp án:** Không. Gatherer là API chính thức từ Java 24; trước đó Java 22/23 chỉ có preview phù hợp với phiên bản tương ứng. Với Java 21, cần nâng JDK hoặc triển khai giải pháp khác bằng Stream API/iterator/collector hiện có.

### Bài 8 — Kiểm tra quyền sở hữu I/O

~~~java
List<Integer> result = Files.lines(path)
        .map(Integer::parseInt)
        .gather(expand())
        .limit(1)
        .toList();
~~~

**Đáp án:** Cần quản lý tài nguyên nguồn bằng `try-with-resources`. `limit(1)` dừng sớm nhưng không tự gọi `close()` trên Stream đọc tệp.

## 20. Ghi nhớ

- `Gatherer.Downstream.push(value)` đẩy một kết quả sang bước tiếp theo và trả `true` nếu downstream **còn muốn nhận thêm**, `false` nếu không.
- `push == false` **không phải lời khẳng định giá trị vừa gửi bị loại**. Nó là tín hiệu *không cần thêm kết quả*.
- Khi phát nhiều kết quả từ một đầu vào, **kiểm tra sau mỗi `push`**; ngừng tạo/phát thêm ngay khi bị từ chối.
- Boolean từ `integrator.integrate` hỏi **có cần thêm đầu vào hay không**; có thể trả `false` vì downstream từ chối hoặc vì gatherer tự dừng.
- Không push một phần tử nhưng vẫn muốn đọc input tiếp theo thì `return true`, không phải `false`.
- `Integrator.ofGreedy` dành cho integrator không tự khởi tạo short-circuit; nó vẫn được phép chuyển tiếp `false` do downstream từ chối.
- `isRejecting()` là tín hiệu best-effort, hữu ích trong finisher; **kết quả của `push`** vẫn là điều phải kiểm tra khi phát.
- Không giữ tham chiếu `Downstream` vượt quá phạm vi callback; tránh state chia sẻ hoặc side effect phụ thuộc lịch chạy.
- Dừng sớm không tự giải phóng nguồn I/O: vẫn cần `try-with-resources`.
- Các ví dụ dùng Stream Gatherers **chính thức trên JDK 24+**, không thể dùng nguyên dạng trên Java 21 hoặc thấp hơn.

**Ý chính:** `Downstream.push` là cơ chế **phối hợp nhu cầu đầu ra** giữa các tầng của pipeline. Một gatherer đúng không chỉ biết phát kết quả, mà còn phải **dừng phát khi downstream đã đủ, truyền tín hiệu dừng ngược về upstream, và phân biệt kết thúc bình thường với lỗi**. Làm đúng các nguyên tắc này giúp gatherer phát nhiều phần tử, tích lũy theo batch hoặc dừng sớm hoạt động dự đoán được và tránh công việc thừa. 

### Tài liệu đối chiếu API

- [JDK 24 — Gatherer.Downstream](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Downstream.html): hợp đồng `push` và `isRejecting`.
- [JDK 24 — Gatherer.Integrator](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.html): ý nghĩa của boolean do integrator trả về.
- [JDK 24 — Gatherer](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html): initializer, integrator, combiner, finisher và quyền sở hữu state/downstream.
- [Dev.java — The Gatherer API](https://dev.java/learn/api/streams/gatherers/): ví dụ ngừng sớm và cách truyền tín hiệu từ chối.
