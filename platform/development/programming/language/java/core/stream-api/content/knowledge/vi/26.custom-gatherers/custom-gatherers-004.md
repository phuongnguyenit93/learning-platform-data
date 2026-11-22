# Phân biệt Integrator thông thường và Integrator.ofGreedy

Trong Java Stream API, `Gatherer` cho phép lập trình viên tự định nghĩa một **thao tác trung gian** (*intermediate operation*) có thể nhận phần tử từ upstream, duy trì trạng thái và phát kết quả sang downstream. Trung tâm của cơ chế này là **`Gatherer.Integrator<A, T, R>`**: một hàm nhận trạng thái `A`, phần tử đầu vào `T` và đối tượng nhận đầu ra `Gatherer.Downstream<R>`.

Khi tạo Integrator, Java cung cấp hai factory rất dễ nhầm:

- **`Gatherer.Integrator.of(...)`:** tạo một Integrator thông thường. Integrator được phép **tự quyết định dừng nhận thêm dữ liệu**, ví dụ khi đạt ngưỡng hoặc thấy một dấu mốc.
- **`Gatherer.Integrator.ofGreedy(...)`:** tạo một Integrator đánh dấu là **`Greedy`**. Nó cam kết **không tự khởi phát dừng sớm**; nếu trả `false` thì nguyên nhân chỉ là downstream không muốn nhận thêm kết quả.

Sự khác biệt này không nằm ở số phần tử phát ra. Greedy Integrator vẫn có thể **lọc bỏ, biến đổi hoặc phát nhiều kết quả** cho một phần tử đầu vào. Điểm khác nhau nằm ở **quyền ra quyết định kết thúc việc nhận dữ liệu từ upstream** và khả năng tối ưu của Stream.

Bài thuộc chương **Xây dựng Gatherer tùy biến** trong mô-đun **JAVA_STREAM_API**. Nội dung nối tiếp kiến thức về pipeline lazy, `filter`, `map`, `reduce`, `collect`, `Spliterator`, trạng thái, xử lý song song và tài nguyên; mục tiêu trực tiếp là sử dụng đúng hợp đồng `of` và `ofGreedy` trước khi tính đến hiệu năng.

> **Phiên bản:** `Stream.gather`, `Gatherer.Integrator` và `Integrator.ofGreedy` là API chính thức từ **Java 24** (JEP 485). Chúng từng ở giai đoạn preview trong Java 22 và 23. Các ví dụ dưới đây được viết cho **JDK 24 trở lên**, không chạy trực tiếp trên Java 17/21.

## 1. Vị trí của Integrator trong một Gatherer

Với một pipeline điển hình:

```text
Nguồn Stream<T>
      |
      | filter(...) / map(...)           (tùy chọn)
      v
  gather(gatherer)
      |
      |  initializer -> tạo trạng thái A
      |  integrator  -> nhận T, cập nhật A, có thể push R
      |  combiner    -> gộp các trạng thái nếu hỗ trợ chia việc
      |  finisher    -> có thể phát thêm R khi kết thúc nguồn
      v
Stream<R>
      |
      | limit(...) / findFirst() / toList() / collect(...)
      v
Kết quả terminal
```

`Gatherer<T, A, R>` có ba kiểu:

| Kiểu | Vai trò | Ví dụ |
| --- | --- | --- |
| `T` | Phần tử đầu vào | `Integer` |
| `A` | Trạng thái nội bộ, có thể mutable | `long[]` lưu tổng chạy |
| `R` | Phần tử được phát sang downstream | `Long` |

Các thành phần khác nhau của Gatherer:

| Thành phần | Công việc |
| --- | --- |
| `initializer()` | Cấp trạng thái mới khi cần |
| `integrator()` | Nhận từng đầu vào, xử lý trạng thái và phát số lượng đầu ra tùy ý |
| `combiner()` | Kết hợp trạng thái nếu Gatherer có thể xử lý song song |
| `finisher()` | Thực hiện công việc cuối nguồn, có thể phát đầu ra bổ sung |

`Integrator` **không** phải một `Collector`. Collector thường tạo kết quả ở terminal operation `collect`, còn Gatherer là giai đoạn trung gian có thể phát nhiều kết quả trước khi toàn bộ nguồn kết thúc.

## 2. Giao diện Integrator và giá trị boolean

Trong Java 24, ý tưởng của chữ ký là:

```java
@FunctionalInterface
interface Integrator<A, T, R> {
    boolean integrate(
        A state,
        T element,
        Gatherer.Downstream<? super R> downstream
    );
}
```

Ba tham số và kết quả có nghĩa:

| Thành phần | Ý nghĩa |
| --- | --- |
| `state` | Trạng thái của Gatherer mà framework cung cấp |
| `element` | Phần tử đầu vào hiện tại |
| `downstream` | Kênh phát `R` cho giai đoạn kế tiếp |
| `return true` | Integrator muốn tiếp tục được cung cấp phần tử |
| `return false` | Integrator muốn **ngừng nhận phần tử tiếp theo** |

Điểm quan trọng: `boolean` **không** biểu diễn “phần tử này có được chọn không”. Một Integrator có thể **không phát phần tử nào** mà vẫn trả `true`, hoặc phát một phần tử rồi trả `false` để dừng ở ranh giới.

```text
integrate(state, element, downstream)
        |
        +-- xử lý element / cập nhật state
        +-- có thể gọi downstream.push(result) nhiều lần
        |
        +-- true: muốn nhận thêm input
        +-- false: yêu cầu kết thúc tích hợp input
```

Với **Integrator thông thường**, `false` có thể đến từ **quyết định riêng** của Integrator hoặc từ tín hiệu downstream. Với **Greedy Integrator**, `false` chỉ có thể là **sự chuyển tiếp tín hiệu downstream từ chối**.

## 3. Downstream.push và Downstream.isRejecting

Hai phương thức liên quan trực tiếp đến hợp đồng của Integrator:

```java
boolean downstream.push(R result);
boolean downstream.isRejecting();
```

- `push(result)` gửi một phần tử đầu ra xuống giai đoạn tiếp theo, **nếu giai đoạn đó còn chấp nhận**.
- `push` trả `true` nếu downstream có thể tiếp tục nhận thêm, `false` nếu downstream đã từ chối.
- Sau khi `push` trả `false`, các lời gọi `push` tiếp theo trên cùng downstream cũng sẽ không được chấp nhận theo hợp đồng.
- `isRejecting()` là phép kiểm tra **best-effort** xem downstream có được biết là đang từ chối hay không. Giá trị `false` không phải cam kết vĩnh viễn rằng một lần `push` trong tương lai sẽ được chấp nhận.

Ví dụ phản hồi hợp lệ:

```java
// Một phần tử vào -> một phần tử ra.
return downstream.push(transformed);
```

Khi downstream có terminal operation như `limit(3).toList()`, một lần `push` có thể báo không muốn nhận thêm. Tại thời điểm đó, Integrator nên tôn trọng tín hiệu để tránh làm việc thừa.

Một nhầm lẫn phổ biến là:

```java
downstream.push(transformed);
return true; // Bỏ qua thông báo downstream có thể đã từ chối.
```

Đoạn này không phải cách tốt để biểu diễn một Integrator luôn tôn trọng downstream. Khi downstream không muốn nhận nữa, việc tiếp tục tính toán hoặc đẩy kết quả mới là thừa và có thể gây tốn tài nguyên. Với Greedy Integrator, **phải phản ánh đúng** trạng thái từ chối của downstream.

## 4. Integrator thông thường: được tự quyết định dừng sớm

Ví dụ nghiệp vụ: từ chuỗi sự kiện, ghi lại mọi sự kiện **cho đến và bao gồm** dấu mốc `"STOP"`, rồi dừng việc duyệt những sự kiện tiếp theo.

```java
import java.util.List;
import java.util.stream.Gatherer;

public class UntilMarkerDemo {

    static Gatherer<String, Void, String> untilMarker(String marker) {
        Gatherer.Integrator<Void, String, String> step =
            Gatherer.Integrator.of(
                (unused, value, downstream) -> {
                    boolean wantsMore = downstream.push(value);

                    // Dừng vì marker, dù downstream chưa hề từ chối.
                    return wantsMore && !value.equals(marker);
                }
            );

        return Gatherer.ofSequential(step);
    }

    public static void main(String[] args) {
        List<String> result = List.of(
                "START", "READY", "STOP", "AFTER", "LATER"
            ).stream()
            .gather(untilMarker("STOP"))
            .toList();

        System.out.println(result); // [START, READY, STOP]
    }
}
```

Chú ý đoạn:

```java
return wantsMore && !value.equals(marker);
```

Hai nguyên nhân khác nhau có thể làm Integrator trả `false`:

1. **Downstream trả `false`** qua `push`: downstream không muốn nhận thêm.
2. **Điều kiện nghiệp vụ gặp marker**: Integrator **tự quyết định** dừng, dù downstream vẫn muốn nhận.

Chính nguyên nhân thứ hai làm Integrator này **không thể được khai báo là Greedy**.

### 4.1. Dừng sớm không đồng nghĩa bỏ phần tử đang xử lý

Integrator ở trên **đẩy marker trước**, sau đó mới trả `false`. Vì vậy `"STOP"` có trong kết quả, còn các phần tử sau marker không được nhận.

Nếu quy tắc là **không bao gồm marker**, có thể kiểm tra trước:

```java
Gatherer.Integrator<Void, String, String> step =
    Gatherer.Integrator.of((unused, value, downstream) -> {
        if (value.equals("STOP")) {
            return false;  // Không push marker.
        }

        return downstream.push(value);
    });
```

Hai phiên bản giải quyết hai hợp đồng nghiệp vụ khác nhau.

### 4.2. Khi nào một Integrator thông thường hợp lý?

- Dừng sau khi nhận `k` kết quả, ngay cả khi downstream chưa đặt `limit(k)`.
- Dừng khi gặp marker kết thúc giao thức.
- Dừng khi chỉ số đạt ngưỡng và không cần đọc thêm đầu vào.
- Dừng khi bộ phân tích xác định phần đầu hợp lệ đã kết thúc.
- Cần một quy tắc short-circuit **phát sinh từ chính logic Gatherer**.

Có thể viết một Integrator thông thường mà **không** bao giờ tự dừng. Khi đó nó vẫn đúng, chỉ là chưa khai báo đặc tính Greedy cho framework biết.

## 5. `Integrator.ofGreedy` thực sự cam kết điều gì?

`Gatherer.Integrator.Greedy<A, T, R>` là **giao diện con** của `Gatherer.Integrator<A, T, R>`. Factory:

```java
Gatherer.Integrator.ofGreedy(greedyIntegrator)
```

trả về đối tượng có kiểu `Gatherer.Integrator.Greedy<A, T, R>`.

Điều kiện cốt lõi là:

> **Greedy Integrator không tự bắt đầu short-circuit. Nó chỉ có thể ngừng nhận thêm dữ liệu khi downstream đã báo từ chối.**

Do đó, những dạng trả về sau phù hợp với Greedy:

```java
// Có phát một kết quả: truyền lại tín hiệu downstream.
return downstream.push(result);

// Không phát gì, downstream chưa bị từ chối.
return true;

// Phát nhiều kết quả: dừng nếu downstream từ chối.
for (R result : results) {
    if (!downstream.push(result)) {
        return false;
    }
}
return true;
```

Trái lại, dạng sau **vi phạm** lời hứa Greedy:

```java
// Không hợp lệ cho ofGreedy: tự dừng vì quy tắc nghiệp vụ.
return downstream.push(result) && !conditionForStop;
```

`conditionForStop` ở đây có thể khiến Integrator trả `false` **dù `push` vừa trả `true`**. Khi đó nguồn dừng do quyết định riêng của Integrator — chính điều mà Greedy cam kết không làm.

### 5.1. Greedy không có nghĩa “phát mọi phần tử”

Greedy mô tả **sự sẵn lòng tiếp tục nhận upstream**, không bắt buộc giữ mọi phần tử.

Ví dụ một Greedy Integrator chỉ phát số chẵn:

```java
import java.util.stream.Gatherer;

Gatherer.Integrator.Greedy<Void, Integer, Integer> evenStep =
    Gatherer.Integrator.ofGreedy(
        (unused, number, downstream) -> {
            if (number % 2 == 0) {
                return downstream.push(number);
            }

            return true; // Bỏ phần tử lẻ, vẫn nhận phần tử tiếp.
        }
    );

Gatherer<Integer, Void, Integer> onlyEven = Gatherer.of(evenStep);
```

`onlyEven` có hành vi tương tự `filter(n -> n % 2 == 0)`. Integrator không push số lẻ, nhưng **không** tự dừng Stream khi thấy số lẻ.

Trong sản phẩm thực tế, hãy ưu tiên `filter` nếu nó đã diễn đạt đủ ý định; ví dụ trên để làm rõ **ngữ nghĩa Greedy**, không khuyến khích thay thế mọi thao tác chuẩn bằng Gatherer tùy chỉnh.

## 6. So sánh `of` và `ofGreedy` theo hợp đồng

| Tiêu chí | `Integrator.of(...)` | `Integrator.ofGreedy(...)` |
| --- | --- | --- |
| Kiểu tạo ra | `Integrator<A,T,R>` | `Integrator.Greedy<A,T,R>` |
| Có thể tự dừng vì điều kiện nghiệp vụ? | **Có** | **Không** |
| Có thể trả `false` khi downstream từ chối? | Có | Có, và đây là nguyên nhân duy nhất phù hợp |
| Có thể không phát đầu ra cho một input? | Có | Có |
| Có thể phát nhiều đầu ra cho một input? | Có | Có |
| Có thể giữ trạng thái mutable nội bộ? | Có, nếu đúng hợp đồng | Có, nếu đúng hợp đồng |
| Có nghĩa tự động chạy song song? | Không | Không |
| Framework phải chú ý `false` của Integrator như yêu cầu tự dừng? | Có | Có thể **không cần kiểm tra** giá trị trả về |
| Có thể hỗ trợ tối ưu? | Có tùy thiết kế | **Thông tin Greedy** mở thêm cơ hội tối ưu |
| Phù hợp khi | Có hoặc có thể có ranh giới kết thúc do Integrator | Chắc chắn không chủ động cắt luồng |

**Điểm then chốt về tối ưu:** Đặc tả Java 24 cho phép triển khai Stream **không kiểm tra boolean do Greedy Integrator trả về**, vì Integrator đã cam kết không tự short-circuit. Downstream có cơ chế riêng để biểu đạt việc không còn nhận kết quả.

Vì thế việc gắn nhãn Greedy sai **không chỉ làm tài liệu kém chính xác**: nó có thể khiến triển khai hợp lệ bỏ qua tín hiệu `false` mà code nghiệp vụ dựa vào. Kết quả sau đó có thể tiếp tục chứa dữ liệu sau điểm đáng lẽ phải dừng.

### 6.1. `ofGreedy` không tự biến đổi logic của lambda

`of` và `ofGreedy` đều nhận lambda có cùng hình dạng ba tham số và trả boolean. Sự khác biệt là **kiểu Integrator** và **cam kết được truyền cho framework**, không phải một thuật toán lọc hay lặp mới.

Một Integrator thường có hành vi Greedy có thể được triển khai bằng `of` và vẫn đúng. Chỉ khi chắc chắn hợp đồng Greedy được thỏa, ta mới nên dùng `ofGreedy` để framework có cơ hội tối ưu.

## 7. Ví dụ đối chiếu: cùng phép ánh xạ, hai kiểu Integrator

Cùng một phép bình phương (ở miền giá trị nhỏ, không tràn):

```java
import java.util.stream.Gatherer;

// Integrator thông thường: hợp lệ, không tự dừng.
Gatherer.Integrator<Void, Integer, Integer> ordinary =
    Gatherer.Integrator.of(
        (unused, n, downstream) -> downstream.push(n * n)
    );

// Greedy Integrator: cũng không tự dừng, báo cho framework biết.
Gatherer.Integrator.Greedy<Void, Integer, Integer> greedy =
    Gatherer.Integrator.ofGreedy(
        (unused, n, downstream) -> downstream.push(n * n)
    );

Gatherer<Integer, Void, Integer> g1 = Gatherer.of(ordinary);
Gatherer<Integer, Void, Integer> g2 = Gatherer.of(greedy);
```

Sử dụng:

```java
import java.util.List;

List<Integer> input = List.of(1, 2, 3, 4);

System.out.println(input.stream().gather(g1).toList());
// [1, 4, 9, 16]

System.out.println(input.stream().gather(g2).toList());
// [1, 4, 9, 16]
```

Đầu ra giống nhau. `g2` cung cấp **thêm thông tin hợp đồng** để triển khai `Stream.gather` có thể tối ưu. **Không có bảo đảm `g2` chạy nhanh hơn** trong mọi tập dữ liệu hoặc mọi JDK.

Nếu không cần quản lý trạng thái hay nhiều đầu ra, `map(n -> n * n)` thông thường là lựa chọn đơn giản nhất.

## 8. Dùng Greedy với bộ lọc: bỏ phần tử không phải dừng Stream

Một lỗi thường gặp khi tự viết filter bằng Gatherer là nhầm “không chọn phần tử này” với “không muốn nhận phần tử tiếp”.

**Sai**:

```java
// Sai: số lẻ làm integrate trả false -> dừng cả phần nguồn.
Gatherer.Integrator<Void, Integer, Integer> wrongFilter =
    Gatherer.Integrator.of(
        (unused, n, downstream) ->
            n % 2 == 0 && downstream.push(n)
    );
```

Với `[2, 3, 4, 6]`, khi gặp `3`, Integrator trả `false`. Nó **không tiếp tục** đến `4` và `6`. Đó là một gatherer kiểu **take-until-failure**, không phải filter.

**Đúng**:

```java
Gatherer.Integrator.Greedy<Void, Integer, Integer> correctFilter =
    Gatherer.Integrator.ofGreedy(
        (unused, n, downstream) ->
            n % 2 == 0 ? downstream.push(n) : true
    );
```

Khi `n` lẻ, không có `push` nên trả `true` để tiếp tục. Khi `n` chẵn, kết quả từ `push` được truyền ngược lên.

Ví dụ này nhấn mạnh: **`return false` luôn có ý nghĩa dừng nhận đầu vào**, không có ý nghĩa “loại một phần tử” trong `Integrator`.

## 9. Greedy phát nhiều kết quả từ một phần tử

Greedy vẫn có thể hoạt động theo kiểu *flat-map*: một phần tử đầu vào sinh ra 0, 1 hoặc nhiều phần tử đầu ra.

Ví dụ mỗi đầu vào là một nhóm chuỗi, cần phát từng chuỗi trong nhóm:

```java
import java.util.List;
import java.util.stream.Gatherer;

Gatherer.Integrator.Greedy<Void, List<String>, String> flattenStep =
    Gatherer.Integrator.ofGreedy(
        (unused, group, downstream) -> {
            for (String item : group) {
                if (!downstream.push(item)) {
                    return false; // Chỉ do downstream từ chối.
                }
            }

            return true; // Nhóm có thể rỗng; vẫn chờ nhóm tiếp.
        }
    );

Gatherer<List<String>, Void, String> flatten = Gatherer.of(flattenStep);

List<String> words = List.of(
        List.of("A", "B"),
        List.of(),
        List.of("C", "D")
    ).stream()
    .gather(flatten)
    .toList();

System.out.println(words); // [A, B, C, D]
```

Lưu ý cách viết:

```java
for (String item : group) {
    if (!downstream.push(item)) {
        return false;
    }
}
return true;
```

Nó truyền tín hiệu từ chối của downstream ngay khi có. Không tiếp tục duyệt hàng nghìn phần tử trong `group` nếu downstream đã báo không cần nhận nữa.

Trong trường hợp chỉ cần làm phẳng một Stream nhóm, `flatMap(List::stream)` đã có sẵn và thường ngắn hơn; Gatherer tùy chỉnh có giá trị khi còn cần quy tắc trạng thái hoặc phát dữ liệu phức tạp.

## 10. Greedy vẫn tôn trọng dừng sớm từ downstream

Hãy phân biệt **dừng do Integrator** và **dừng do terminal/downstream**.

Ví dụ một nguồn vô hạn:

```java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

Gatherer.Integrator.Greedy<Void, Integer, Integer> squareStep =
    Gatherer.Integrator.ofGreedy(
        (unused, value, downstream) -> downstream.push(value * value)
    );

List<Integer> firstThree = Stream.iterate(1, n -> n + 1)
    .gather(Gatherer.of(squareStep))
    .limit(3)
    .toList();

System.out.println(firstThree); // [1, 4, 9]
```

`squareStep` không có quy tắc dừng riêng: nếu downstream cần thêm, nó sẵn sàng nhận input tiếp. Nhưng `limit(3)` không muốn nhận thêm sau ba phần tử kết quả, nên pipeline có thể kết thúc.

**Không được nói rằng Greedy “luôn phải duyệt hết nguồn bất kể downstream”.** Với nguồn vô hạn, câu đó dẫn đến mâu thuẫn ngay ở ví dụ này. Greedy chỉ nói rằng **bản thân Integrator không đặt ranh giới kết thúc độc lập với downstream**.

### 10.1. Điều gì xảy ra khi downstream không muốn nhận nữa?

Giả sử Greedy Integrator phát nhiều phần tử và `limit(2)` nằm sau:

```java
List<String> firstTwo = List.of(
        List.of("A", "B", "C"),
        List.of("D")
    ).stream()
    .gather(flatten)
    .limit(2)
    .toList();

System.out.println(firstTwo); // [A, B]
```

Khi `push` báo từ chối, vòng lặp trong `flattenStep` trả `false` ngay. Việc truyền boolean này **không vi phạm Greedy**, vì nó chỉ phản ánh quyết định của downstream.

Không dùng phép đếm side effect trong mapper, `peek` hoặc `integrate` làm cách kiểm chứng chắc chắn số phần tử đã được duyệt: Stream có quyền tối ưu các giai đoạn khi không thay đổi ngữ nghĩa công khai.

## 11. Vi phạm hợp đồng `ofGreedy` nguy hiểm thế nào?

Xem đoạn mã **cố ý sai**:

```java
// KHÔNG NÊN DÙNG.
Gatherer.Integrator.Greedy<Void, String, String> bad =
    Gatherer.Integrator.ofGreedy(
        (unused, value, downstream) -> {
            boolean accepted = downstream.push(value);

            // Sai: false có thể đến từ STOP dù downstream vẫn chấp nhận.
            return accepted && !"STOP".equals(value);
        }
    );
```

Lập trình viên muốn cắt tại `"STOP"`, nhưng đã khai báo `Greedy`. Đặc tả cho phép triển khai Stream **không kiểm tra giá trị boolean của Greedy Integrator**. Vì vậy, mã này **không được bảo đảm** sẽ dừng ở marker.

Cách sửa:

```java
Gatherer.Integrator<Void, String, String> correct =
    Gatherer.Integrator.of(
        (unused, value, downstream) ->
            downstream.push(value) && !"STOP".equals(value)
    );
```

Hoặc cân nhắc `takeWhile` nếu nguồn có encounter order và quy tắc nghiệp vụ phù hợp với việc lấy tiền tố (không bao gồm phần tử đầu không thỏa). Nếu phải **giữ marker**, custom Integrator như trên là một cách diễn đạt trực tiếp.

### 11.1. Những kiểu vi phạm tương tự

| Mẫu sai | Vì sao vi phạm |
| --- | --- |
| `ofGreedy(... -> count < limit)` | Tự dừng khi đạt limit, không do downstream |
| `ofGreedy(... -> !isEndMarker(element))` | Tự dừng vì marker |
| `ofGreedy(... -> !businessRuleFailed)` | Tự dừng vì thất bại nghiệp vụ |
| `ofGreedy(... -> downstream.push(x) && count < limit)` | Có thể trả `false` vì count dù `push` trả `true` |
| `ofGreedy(... -> false)` | Luôn tự dừng ngay nếu downstream chưa từ chối |

**Quy tắc review:** Mỗi nhánh có thể `return false` trong Greedy Integrator phải được truy ngược về **lời gọi `downstream.push(...)` đã trả `false`**. Nếu tồn tại một nhánh `false` do bộ đếm, điều kiện nghiệp vụ hoặc ngoại lệ quy đổi thành boolean, hãy dùng Integrator thông thường hoặc thay đổi thiết kế.

## 12. Greedy và trạng thái: ví dụ tổng chạy

Greedy **không có nghĩa stateless**. Một Integrator có thể có trạng thái riêng và vẫn luôn muốn nhận thêm phần tử, miễn là downstream còn nhận.

Ví dụ tổng tích lũy sau mỗi phần tử:

```java
import java.util.List;
import java.util.stream.Gatherer;

public class RunningTotalDemo {

    static Gatherer<Integer, long[], Long> runningTotal() {
        Gatherer.Integrator.Greedy<long[], Integer, Long> step =
            Gatherer.Integrator.ofGreedy(
                (state, value, downstream) -> {
                    state[0] = Math.addExact(state[0], (long) value);
                    return downstream.push(state[0]);
                }
            );

        return Gatherer.ofSequential(
            () -> new long[] {0L},
            step
        );
    }

    public static void main(String[] args) {
        List<Long> totals = List.of(3, 5, 7)
            .stream()
            .gather(runningTotal())
            .toList();

        System.out.println(totals); // [3, 8, 15]
    }
}
```

Đặc điểm quan trọng:

- `initializer` tạo mảng trạng thái **mới** cho mỗi lượt xử lý được quản lý.
- `integrate` cập nhật tổng và phát giá trị mới qua `push`.
- `Math.addExact` ném `ArithmeticException` nếu tổng vượt miền `long`; Greedy không liên quan đến việc phát hiện tràn số.
- `ofSequential` được chọn vì tổng chạy phụ thuộc thứ tự và ví dụ **không định nghĩa combiner**.
- `ofGreedy` được chọn vì integrator **không có điều kiện tự dừng**; nó chỉ trả tín hiệu từ `push`.

Cả hai lựa chọn **`ofSequential`** và **`ofGreedy`** đều xuất hiện trong ví dụ nhưng giải quyết **hai câu hỏi khác nhau**:

| Câu hỏi | Lựa chọn |
| --- | --- |
| Có thể chia và gộp trạng thái để chạy song song đúng không? | `ofSequential` hoặc thiết kế `of` với combiner hợp lệ |
| Integrator có tự khởi phát short-circuit không? | `Integrator.of` hoặc `Integrator.ofGreedy` |

Nếu chỉ cần running total thông thường, `Gatherers.scan(() -> 0L, Long::sum)` đã thực hiện ý tưởng tương tự và thường nên được ưu tiên.

## 13. Greedy và finisher: không phát trong integrator vẫn hợp lệ

Có những Gatherer **tích lũy toàn bộ nguồn rồi mới phát một kết quả** trong finisher. Integrator của chúng có thể không gọi `downstream.push` lần nào.

Ví dụ đếm số phần tử đầu vào và phát kết quả lúc kết thúc:

```java
import java.util.List;
import java.util.stream.Gatherer;

public class CountAtEndDemo {
    static final class State {
        long count;
    }

    static Gatherer<String, State, Long> countAtEnd() {
        Gatherer.Integrator.Greedy<State, String, Long> step =
            Gatherer.Integrator.ofGreedy(
                (state, value, downstream) -> {
                    state.count = Math.addExact(state.count, 1L);
                    return true; // Không push, không có lý do tự dừng.
                }
            );

        return Gatherer.ofSequential(
            State::new,
            step,
            (state, downstream) -> {
                if (!downstream.isRejecting()) {
                    downstream.push(state.count);
                }
            }
        );
    }

    public static void main(String[] args) {
        List<Long> result = List.of("A", "B", "C")
            .stream()
            .gather(countAtEnd())
            .toList();

        System.out.println(result); // [3]
    }
}
```

`Integrator.ofGreedy` phù hợp ở đây dù nó **không phát dữ liệu ở mỗi bước**. Nó tiếp tục nhận input và cập nhật trạng thái; đến cuối nguồn, `finisher` phát tổng số lượng.

### 13.1. Vì sao finisher cũng phải quan tâm đến downstream?

`finisher` có thể được gọi khi downstream không còn nhận thêm dữ liệu, tùy cách kết thúc pipeline. Với công việc phát nhiều kết quả trong finisher, nên kiểm tra `downstream.isRejecting()` nếu hữu ích và đặc biệt kiểm tra boolean từ mỗi `downstream.push(...)` để dừng việc phát khi bị từ chối.

`isRejecting()` là tín hiệu best-effort, nên vẫn phải sử dụng `push` đúng hợp đồng; không lưu `Downstream` vào một biến toàn cục hoặc giữ tham chiếu sau khi lời gọi callback kết thúc.

### 13.2. Nếu chỉ cần đếm, không nên viết Gatherer

Ví dụ trên minh họa trạng thái và finisher. Với bài toán thật, gọi:

```java
long count = List.of("A", "B", "C")
    .stream()
    .count();

System.out.println(count); // 3
```

ngắn, rõ và cho phép Stream tự tối ưu. Gatherer có ích khi một phép biến đổi **trung gian** có hợp đồng riêng mà `filter`, `map`, `reduce` hay `collect` dựng sẵn không đáp ứng.

## 14. Integrator thông thường có thể “hành xử Greedy” mà vẫn đúng

Ví dụ:

```java
Gatherer.Integrator<Void, Integer, Integer> normal =
    Gatherer.Integrator.of(
        (unused, n, downstream) -> downstream.push(n + 1)
    );
```

`normal` **không tự dừng**. Nó vẫn là một Integrator thông thường vì được tạo qua `of`, nhưng hành vi phù hợp lời hứa Greedy.

Nếu đã kiểm tra chắc chắn rằng Integrator không tự short-circuit, có thể viết:

```java
Gatherer.Integrator.Greedy<Void, Integer, Integer> greedy =
    Gatherer.Integrator.ofGreedy(
        (unused, n, downstream) -> downstream.push(n + 1)
    );
```

Cả hai đều hợp lệ và cho cùng kết quả trên dữ liệu tương ứng. Khác biệt là `greedy` làm **tính chất không tự dừng** trở thành thông tin kiểu mà triển khai có thể dựa vào.

**Chiến lược thực tế:** Khi chưa chắc các nhánh kết thúc của một Integrator có đúng hợp đồng Greedy hay không, **bắt đầu bằng `Integrator.of`**. Chỉ chuyển sang `ofGreedy` sau khi rà soát tất cả đường trả về và có kiểm thử phù hợp.

## 15. Greedy không đồng nghĩa song song, và `ofSequential` không đồng nghĩa non-greedy

Đây là hai trục độc lập:

```text
                             CÓ THỂ TỰ SHORT-CIRCUIT?
                                   |
                          Có                 Không
                           |                   |
          Có combiner   Integrator.of      Integrator.ofGreedy
          hợp lệ          + Gatherer.of       + Gatherer.of
                           |
          Sequential    Integrator.of      Integrator.ofGreedy
          (không          + ofSequential     + ofSequential
          combiner)
```

Đọc sơ đồ theo hai câu hỏi:

1. **Tính chất Integrator**: có tự dừng nhận dữ liệu không? Nếu có, không khai báo Greedy.
2. **Khả năng chia trạng thái**: có combiner hợp lệ hay chỉ xử lý tuần tự? Điều này phụ thuộc cách tạo **Gatherer**, không phụ thuộc tên `ofGreedy`.

`Gatherer.of(integrator)` cho **Gatherer stateless có thể parallelize** theo hợp đồng. `Gatherer.ofSequential(initializer, integrator)` tạo một **Gatherer tuần tự** khi chưa có cách chia/gộp trạng thái hợp lệ.

Nếu code có một mảng `long[]` làm tổng chạy, không được đổi `ofSequential` sang một phương án chạy song song chỉ vì Integrator đã được đánh dấu Greedy. Các cửa sổ hoặc tổng chạy phụ thuộc thứ tự cần một thuật toán combiner đúng, không chỉ một nhãn tối ưu.

### 15.1. `Spliterator.CONCURRENT` và Greedy cũng khác nhau

- `Spliterator.CONCURRENT` mô tả **nguồn có thể bị sửa đồng thời** theo hợp đồng nguồn.
- `Collector.Characteristics.CONCURRENT` mô tả bộ tích lũy cho phép cập nhật đồng thời theo hợp đồng collector.
- `Gatherer.Integrator.Greedy` mô tả **không tự bắt đầu short-circuit**.

Không có đặc tính nào trong ba đặc tính này tự động kéo theo hai đặc tính còn lại.

## 16. Short-circuit từ upstream và downstream

Pipeline có thể có giới hạn ở nhiều vị trí khác nhau:

```java
Stream.of(1, 2, 3, 4, 5)
    .takeWhile(n -> n < 4)
    .gather(greedyGatherer)
    .limit(2)
    .toList();
```

Hãy tách ba nguồn kết thúc:

- **Upstream `takeWhile`** có thể ngừng cung cấp đầu vào khi predicate sai.
- **Greedy Integrator** không tự yêu cầu ngừng; nó xử lý những phần tử được cung cấp.
- **Downstream `limit(2)`** có thể ngừng muốn nhận đầu ra sau khi đủ hai phần tử.

Do đó, câu “Greedy nhận hết nguồn” chỉ đúng khi nguồn thực sự tiếp tục cung cấp phần tử và downstream còn nhận; nó **không** có nghĩa chạy hết toàn bộ nguồn vật lý trong mọi pipeline.

### 16.1. Vì sao vẫn phải truyền tín hiệu từ `push`?

Giả sử đầu ra của Gatherer rất đắt để tính. Nếu `push` trả `false` sau khi terminal operation đã đủ dữ liệu, việc tiếp tục tính những kết quả còn lại chỉ gây lãng phí. Với một Greedy Integrator, trả lại giá trị `push` thể hiện rõ việc tôn trọng downstream:

```java
return downstream.push(expensiveResult);
```

Triển khai Stream có thể bỏ qua boolean của Greedy Integrator, nhưng bản thân downstream vẫn quản lý trạng thái từ chối. Vì vậy **không được tận dụng điểm này để lờ tín hiệu `push`** rồi thực hiện thêm công việc có tác dụng phụ.

## 17. Lỗi điển hình và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `ofGreedy` cho gatherer dừng ở marker | Vi phạm cam kết không tự dừng; boolean có thể bị bỏ qua | Dùng `Integrator.of` |
| Dùng `ofGreedy` rồi trả `false` khi gặp phần tử không hợp lệ nhưng muốn bỏ qua | Có thể kết thúc hoặc cho hành vi không được bảo đảm | Không push và trả `true` khi chỉ muốn lọc |
| Dùng `of` rồi trả `false` cho phần tử bị lọc | Dừng luôn luồng thay vì chỉ bỏ một phần tử | Không push, trả `true` |
| Luôn `return true` sau `downstream.push(...)` | Không phản ánh downstream từ chối | Trả `push` hoặc ngừng vòng lặp khi `push` trả `false` |
| Hiểu `ofGreedy` nghĩa là phải push đúng một phần tử | Không hiểu lọc, flatten, finisher | Nhớ Greedy là hợp đồng **không tự dừng** |
| Hiểu `ofGreedy` nghĩa là xử lý nhanh hơn trong mọi trường hợp | Tối ưu không được bảo đảm | Đo bằng workload đại diện |
| Cho rằng Greedy tự động thread-safe | Có thể có trạng thái chia sẻ sai | Quản lý initializer/combiner và confinement riêng |
| Cho rằng `ofSequential` không được dùng Greedy | Bỏ lỡ cơ hội diễn đạt hợp đồng | Hai trục độc lập |
| Đánh dấu Greedy khi có `return count < limit` | False do điều kiện nội bộ | Đổi sang Integrator thường |
| Không kiểm tra `push` khi phát nhiều kết quả | Làm việc vô ích sau downstream từ chối | Dừng vòng lặp nếu `push` trả `false` |
| Giữ `state` hoặc `downstream` trong biến static để dùng về sau | Vi phạm hợp đồng vòng đời, dễ data race | Chỉ dùng tham chiếu trong phạm vi callback hợp lệ |
| Dùng `peek`/side effect để đo số lần Integrator được gọi | Pipeline có thể short-circuit hoặc tối ưu | Kiểm thử kết quả công khai |
| Dùng `gather` trên JDK 17/21 | API chưa tồn tại | Dùng JDK 24+ hoặc thuật toán tương thích |
| Trả tài nguyên I/O mà không có close handler/hợp đồng sở hữu | Rò rỉ tệp, cursor hoặc kết nối | Dùng `try-with-resources` và API nguồn đúng |
| Dùng phép cộng kiểu `int`/`long` và cho rằng Greedy ngăn tràn | Kết quả có thể sai/tràn | `Math.addExact`, `BigInteger` theo nghiệp vụ |

## 18. Ví dụ Java 24 hoàn chỉnh: cả hai loại Integrator

Ví dụ sau có thể lưu thành `GreedyVsOrdinaryDemo.java` và biên dịch bằng **JDK 24**. Nó cho thấy cả Integrator thông thường **tự dừng** lẫn Greedy Integrator **tiếp tục cho đến khi downstream từ chối**.

```java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class GreedyVsOrdinaryDemo {

    // Không tự dừng: mỗi số chẵn được biến thành bình phương.
    static Gatherer<Integer, Void, Integer> evenSquares() {
        Gatherer.Integrator.Greedy<Void, Integer, Integer> step =
            Gatherer.Integrator.ofGreedy(
                (unused, n, downstream) -> {
                    if (n % 2 != 0) {
                        return true;   // Bỏ qua số lẻ, không dừng.
                    }

                    return downstream.push(Math.multiplyExact(n, n));
                }
            );

        return Gatherer.of(step);
    }

    // Tự dừng sau marker, kể cả khi downstream vẫn muốn nhận.
    static Gatherer<String, Void, String> untilStop(String marker) {
        Gatherer.Integrator<Void, String, String> step =
            Gatherer.Integrator.of(
                (unused, text, downstream) -> {
                    boolean wantsMore = downstream.push(text);
                    return wantsMore && !text.equals(marker);
                }
            );

        return Gatherer.ofSequential(step);
    }

    // Có trạng thái, nhưng không tự dừng.
    static Gatherer<Integer, long[], Long> runningTotals() {
        Gatherer.Integrator.Greedy<long[], Integer, Long> step =
            Gatherer.Integrator.ofGreedy(
                (state, n, downstream) -> {
                    state[0] = Math.addExact(state[0], (long) n);
                    return downstream.push(state[0]);
                }
            );

        return Gatherer.ofSequential(
            () -> new long[] {0L},
            step
        );
    }

    public static void main(String[] args) {
        System.out.println(
            List.of(1, 2, 3, 4, 5, 6).stream()
                .gather(evenSquares())
                .toList()
        ); // [4, 16, 36]

        System.out.println(
            List.of("A", "B", "STOP", "C").stream()
                .gather(untilStop("STOP"))
                .toList()
        ); // [A, B, STOP]

        System.out.println(
            List.of(3, 5, 7).stream()
                .gather(runningTotals())
                .toList()
        ); // [3, 8, 15]

        System.out.println(
            Stream.iterate(1, n -> n + 1)
                .gather(evenSquares())
                .limit(3)
                .toList()
        ); // [4, 16, 36]
    }
}
```

Biên dịch và chạy:

```bash
javac --release 24 GreedyVsOrdinaryDemo.java
java GreedyVsOrdinaryDemo
```

Nhận xét:

1. `evenSquares` là Greedy vì **loại số lẻ không làm nó dừng nhận số tiếp**, và các số chẵn chỉ chuyển tín hiệu từ `push`.
2. `untilStop` là Integrator thông thường vì **marker làm nó tự dừng**.
3. `runningTotals` là Greedy **có trạng thái**, sử dụng `ofSequential` để không đòi một combiner cho tổng chạy.
4. Nguồn `Stream.iterate` là vô hạn, nhưng `limit(3)` downstream có thể dừng pipeline sau ba bình phương chẵn.
5. Kết quả được kiểm chứng qua **danh sách đầu ra**, không dựa vào số lần gọi lambda hoặc thread thực thi.

## 19. Kiểm thử hợp đồng Greedy và dừng sớm

Với mã sản xuất, cần kiểm thử riêng **tính đúng của kết quả** và **quy tắc kết thúc**.

### 19.1. Các test dữ liệu nhỏ

| Đầu vào | Gatherer | Kết quả mong đợi |
| --- | --- | --- |
| `[]` | `evenSquares` | `[]` |
| `[1,3,5]` | `evenSquares` | `[]` |
| `[2,3,4]` | `evenSquares` | `[4,16]` |
| `["A","STOP","B"]` | `untilStop("STOP")` | `["A","STOP"]` |
| `["A","B"]` | `untilStop("STOP")` | `["A","B"]` |
| `[1,2,3]` | `runningTotals` | `[1,3,6]` |
| `[1,2,3,4]` rồi `limit(2)` | `evenSquares` | `[4,16]` |

Kiểm tra các tình huống:

- Nguồn rỗng và chỉ một phần tử.
- Predicate lọc không khớp hoặc khớp tất cả.
- Marker ở đầu, giữa, cuối hoặc không có marker.
- Downstream `limit(0)`, `limit(1)`, `findFirst`.
- Một Integrator phát **nhiều kết quả** cho một phần tử đầu vào.
- Phát sinh ngoại lệ trong mapper hoặc khi đẩy dữ liệu.
- Chạy trên nguồn có thứ tự; không suy đoán thứ tự nếu dùng `unordered()`.

### 19.2. Đừng dựa vào việc “mã sai vẫn có vẻ chạy đúng”

Một Greedy Integrator vi phạm hợp đồng có thể **tình cờ** dừng đúng trong một phiên bản JVM hoặc một trường hợp test. Điều đó không chứng minh mã hợp lệ, vì triển khai khác **được phép bỏ qua boolean** của Greedy Integrator.

Do đó, bên cạnh các test đầu ra, phải có bước **review mọi đường `return false`** của Integrator trước khi gọi `ofGreedy`. Đây là kiểm tra hợp đồng, không chỉ kiểm tra ví dụ.

### 19.3. Kiểm tra tính đúng khi song song

Nếu Gatherer có combiner cho phép chạy song song, hãy so sánh ngữ nghĩa của pipeline tuần tự và song song trên dữ liệu có thứ tự khi nghiệp vụ yêu cầu encounter order.

Đặc biệt với tập dữ liệu lớn và quy tắc short-circuit, cần xác minh rằng các đầu ra của nhánh sau điểm dừng không bị giữ lại sai hợp đồng. Không đặt trạng thái `HashMap` hoặc `ArrayList` toàn cục để các worker cùng ghi, và không lạm dụng `AtomicInteger` để biến side effect thành cách tổng hợp chính.

## 20. Hiệu năng và khả năng tối ưu

Thông tin Greedy có thể giúp triển khai Stream tối ưu cách điều phối giai đoạn gather. Tuy nhiên:

- **Không có lời hứa định lượng** rằng `ofGreedy` nhanh hơn `of`.
- Tối ưu thực tế phụ thuộc downstream, độ dài nguồn, số kết quả phát ra và các giai đoạn khác.
- Nếu Integrator có tính toán nặng hoặc nguồn đọc I/O, chi phí đó có thể lớn hơn phần tiết kiệm từ việc không cần kiểm tra boolean.
- Việc chuyển sang `ofGreedy` **không** tự mở khả năng song song cho Gatherer đã được tạo với `ofSequential`.
- Greedy không thay thế phép `filter`/`map` chuẩn, vốn có thể được triển khai tối ưu hơn cho trường hợp đơn giản.

Khi thực sự cần đo hiệu năng, dùng dữ liệu đại diện, thử nhiều lần và công cụ phù hợp như JMH. Trước khi so tốc độ phải bảo đảm hai phiên bản **có cùng kết quả và cùng hợp đồng dừng**, không đổi `of` thành `ofGreedy` với một Integrator vốn tự short-circuit.

### 20.1. Nguồn có tài nguyên vẫn phải được đóng

Khi nguồn là `Files.lines(path)` hoặc một Stream từ tài nguyên cần giải phóng, terminal operation `toList()`, `findFirst()` hoặc một lần dừng sớm từ Integrator **không tự thay thế `close()`**.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

// Đặt trong phương thức có throws IOException hoặc xử lý lỗi.
Path file = Path.of("events.txt");

try (Stream<String> lines = Files.lines(file)) {
    List<String> untilStop = lines
        .gather(GreedyVsOrdinaryDemo.untilStop("STOP"))
        .toList();

    System.out.println(untilStop);
}
```

`try-with-resources` đóng nguồn tệp cả khi Gatherer dừng sớm hay khi lambda phát sinh ngoại lệ. Nếu API trả Stream còn sống, quyền sở hữu và trách nhiệm đóng phải được xác định trong hợp đồng API.

## 21. Bài tập thực hành

### Bài 1: Phân loại Integrator

Cho bốn lambda:

```java
// A
(unused, n, downstream) -> downstream.push(n)

// B
(unused, n, downstream) -> n >= 0 && downstream.push(n)

// C
(unused, n, downstream) -> n >= 0
    ? downstream.push(n)
    : true

// D
(unused, n, downstream) -> {
    if (n == 100) return false;
    return downstream.push(n);
}
```

Hãy xác định lambda nào có thể khai báo `ofGreedy` và vì sao. Phân biệt trường hợp **lọc** với trường hợp **tự dừng**.

### Bài 2: Chuyển từ `of` sang `ofGreedy`

Viết Integrator thường phát chuỗi viết hoa:

```java
Gatherer.Integrator<Void, String, String> upper =
    Gatherer.Integrator.of(
        (unused, s, downstream) ->
            downstream.push(s.toUpperCase())
    );
```

Chuyển nó sang `ofGreedy` và so sánh kết quả khi downstream là `limit(2).toList()`. Giải thích vì sao không nên suy từ kết quả bằng nhau rằng hiệu năng chắc chắn bằng nhau hoặc nhanh hơn.

### Bài 3: Marker dừng sớm

Viết Gatherer phát các dòng log cho đến `"END"`, bao gồm marker, rồi dừng. Dùng `Integrator.of`. Vì sao dùng `ofGreedy` sẽ vi phạm hợp đồng?

### Bài 4: Phát nhiều đầu ra

Tạo Greedy Gatherer tách một `List<String>` thành từng chuỗi. Dùng `limit(3)` sau Gatherer để kiểm tra việc dừng phát khi downstream từ chối. Giải thích vai trò của boolean từ `push`.

### Bài 5: Lọc phần tử không hợp lệ

Cho `[2, -1, 4, -3, 6]`. Viết Greedy Integrator chỉ phát số không âm; kết quả phải là `[2,4,6]`. Thử dùng `return false` khi số âm và giải thích vì sao nó không còn là phép lọc đúng.

### Bài 6: Tổng chạy có trạng thái

Tạo `Gatherer<Integer, long[], Long>` dùng `ofSequential` và `ofGreedy` phát tổng sau từng số. Kiểm thử `[1,2,3]`, nguồn rỗng và số âm. Nếu có nguy cơ tràn `long` thì thiết kế xử lý như thế nào?

### Bài 7: Finisher chỉ phát kết quả cuối

Tạo Gatherer dùng `initializer` giữ bộ đếm, `ofGreedy` tăng đếm nhưng **không push**, rồi `finisher` phát kết quả. Khi nào nên thay Gatherer đó bằng `Stream.count()` hoặc `Collectors.counting()`?

### Bài 8: Lỗi hợp đồng khó phát hiện

Cho:

```java
Gatherer.Integrator.ofGreedy(
    (state, item, downstream) -> {
        state.processed++;
        boolean more = downstream.push(item);
        return more && state.processed < 10;
    }
);
```

Giải thích vì sao đoạn này không hợp lệ dù đôi khi có thể dừng đúng sau 10 phần tử. Viết lại bằng Integrator thường hoặc bỏ giới hạn nội bộ để chỉ còn việc phản ánh downstream.

### Bài 9: Thứ tự và chia việc

Một Gatherer tích lũy prefix sum bằng `long[]` nhưng không có combiner chính xác. Nó có nên dùng `ofSequential` không? Có thể dùng `ofGreedy` cho Integrator của nó không? Vì sao hai câu trả lời độc lập?

### Bài 10: Đánh giá tối ưu

Thiết kế benchmark so sánh Integrator thường có hành vi Greedy và Integrator được đánh dấu `Greedy` trên cùng dữ liệu. Nêu các điều kiện phải giữ cố định: JDK, đầu vào, downstream, kích thước, mức độ song song và tính đúng kết quả.

## 22. Tự kiểm tra kiến thức

- `Gatherer.Integrator<A,T,R>` nhận ba đối số nào và trả kết quả kiểu gì?
- `return false` trong `integrate` có ý nghĩa “bỏ phần tử hiện tại” hay “ngừng nhận thêm đầu vào”?
- Điều gì phân biệt `Integrator.of` và `Integrator.ofGreedy`?
- Có thể dùng Greedy để bỏ qua một phần tử nhưng vẫn xử lý các phần tử sau đó không?
- Greedy có thể phát nhiều phần tử đầu ra cho một phần tử đầu vào không?
- Tại sao `ofGreedy` không phù hợp với thuật toán “dừng ở marker”?
- Vì sao một triển khai Stream được phép bỏ qua boolean của Greedy Integrator?
- `downstream.push` trả `false` có ý nghĩa gì?
- `isRejecting()` có phải một bảo đảm tuyệt đối về mọi lần `push` tương lai không?
- Có thể xây một Greedy Integrator có trạng thái nội bộ không?
- `ofSequential` quyết định điều gì mà `ofGreedy` không quyết định?
- Vì sao nguồn dùng `Spliterator.CONCURRENT` không làm một Integrator tự nhiên thread-safe?
- Khi nào nên dùng `filter`, `map` hoặc `count` thay vì Gatherer tùy chỉnh?
- Khi nguồn là `Files.lines`, ai chịu trách nhiệm đóng sau short-circuit?
- Những trường hợp kiểm thử nào giúp phát hiện một Gatherer tự dừng sai hợp đồng?

## 23. Tài liệu tham khảo chính thức

- [Java SE 24 — Gatherer.Integrator](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.html): chữ ký `integrate`, `of` và `ofGreedy`.
- [Java SE 24 — Gatherer.Integrator.Greedy](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.Greedy.html): cam kết không tự short-circuit.
- [Java SE 24 — Gatherer.Downstream](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Downstream.html): `push` và `isRejecting`.
- [Java SE 24 — Gatherer](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html): hợp đồng initializer/integrator/combiner/finisher và tối ưu Greedy.
- [Oracle — Stream Gatherers Guide](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html): ví dụ Integrator, short-circuit, finisher và parallel.
- [Dev.java — The Gatherer API](https://dev.java/learn/api/streams/gatherers/): hướng dẫn về Greedy Integrators và cách truyền tín hiệu downstream.
- [JEP 485 — Stream Gatherers](https://openjdk.org/jeps/485): chuẩn hóa API trong Java 24.

**Ghi nhớ:** `Integrator.of(...)` dùng cho Integrator **có thể tự dừng nhận input**; `Integrator.ofGreedy(...)` dùng khi Integrator **không bao giờ tự khởi phát short-circuit**, chỉ phản ánh việc downstream từ chối. Greedy **không** có nghĩa luôn phát một phần tử, không tự động song song hay thread-safe và không bảo đảm tăng tốc. Việc khai báo Greedy sai có thể làm kết quả sai vì framework **được phép bỏ qua boolean** của nó. Hãy ưu tiên tính đúng của hợp đồng và chỉ dùng `ofGreedy` khi tất cả đường trả về của Integrator đều phù hợp.
