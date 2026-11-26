# Phát không, một hoặc nhiều phần tử đầu ra qua Downstream.push

**Gatherer** là phép toán trung gian của Stream API, cho phép một phần tử đầu vào tạo ra không, một hoặc nhiều phần tử đầu ra. Trong custom Gatherer, hàm **integrator** nhận từng phần tử và dùng **Gatherer.Downstream.push(...)** để chuyển kết quả sang bước tiếp theo của pipeline.

Stream Gatherers xuất hiện dưới dạng preview ở Java 22 qua JEP 461, tiếp tục preview ở Java 23 và trở thành API ổn định từ Java 24 qua JEP 485. Các ví dụ trong bài dùng API final thuộc **java.util.stream**, chạy trực tiếp trên JDK 24 trở lên, bao gồm JDK 25 LTS và JDK 27; không cần bật preview.

## 1. Downstream là bước tiếp theo của pipeline

Một Gatherer biến đổi stream đầu vào thành stream đầu ra. Kết quả mà nó phát ra sẽ được chuyển đến operation tiếp theo, chẳng hạn **map**, **filter**, **limit** hoặc terminal operation.

Trong integrator, tham số **downstream** có kiểu **Gatherer.Downstream**. Gọi **downstream.push(value)** để gửi một phần tử sang bước tiếp theo:

~~~java
downstream.push(result);
~~~

Một lần gọi integrator có thể:

- Không gọi **push**: phần tử đầu vào không tạo ra đầu ra.
- Gọi **push** một lần: một phần tử đầu vào tạo ra một phần tử đầu ra.
- Gọi **push** nhiều lần: một phần tử đầu vào tạo ra nhiều phần tử đầu ra.

Gatherer vì vậy hỗ trợ nhiều kiểu biến đổi: one-to-one, one-to-many, many-to-one và many-to-many. Trạng thái trung gian cho phép một phần tử đầu vào ảnh hưởng đến kết quả của các phần tử tiếp theo.

## 2. Phân biệt hai giá trị boolean

Một điểm dễ nhầm là **Downstream.push(...)** và **Integrator.integrate(...)** đều trả về boolean, nhưng hai giá trị này diễn tả hai việc khác nhau.

| Phương thức | Trả về true | Trả về false |
|---|---|---|
| **downstream.push(element)** | Downstream đã nhận phần tử và vẫn có thể nhận thêm | Downstream không nhận thêm phần tử nào nữa |
| **integrate(state, element, downstream)** | Gatherer muốn tiếp tục nhận phần tử đầu vào tiếp theo | Gatherer dừng tiêu thụ đầu vào, tức short-circuit |

Quy tắc thực hành:

1. Nếu không phát đầu ra cho phần tử hiện tại, integrator thường trả về **true** để xử lý phần tử đầu vào tiếp theo.
2. Nếu gọi **push** và nhận **false**, hãy dừng phát thêm đầu ra ngay lập tức và trả về **false** từ integrator.
3. Nếu phát xong một hoặc nhiều đầu ra và downstream vẫn chấp nhận thêm, trả về **true** để tiếp tục.

Ví dụ Gatherer chỉ phát số chẵn; số lẻ không gọi **push**:

~~~java
static Gatherer<Integer, ?, Integer> evenOnly() {
    return Gatherer.<Integer, Integer>of(
            Gatherer.Integrator.<Void, Integer, Integer>of(
                    (unused, element, downstream) -> {
                        if (element % 2 != 0) {
                            return true;
                        }
                        return downstream.push(element);
                    }
            )
    );
}
~~~

Nếu downstream đã trả về **false**, những lần gọi **push** tiếp theo cũng trả về **false**. Không nên bỏ qua giá trị trả về của **push**, vì Gatherer có thể tiếp tục làm việc trên đầu vào dù bước tiếp theo đã dừng nhận dữ liệu.

## 3. Ví dụ một Gatherer phát không, một hoặc nhiều phần tử

Có thể định nghĩa một Gatherer lặp lại mỗi phần tử đầu vào theo số lần cấu hình. Cùng một implementation minh họa cả ba trường hợp: không phát, phát một lần và phát nhiều lần.

~~~java
import java.util.stream.Gatherer;
import java.util.stream.Stream;

class RepeatGatherer {
    static <T> Gatherer<T, ?, T> repeat(int copies) {
        if (copies < 0) {
            throw new IllegalArgumentException("copies must be >= 0");
        }

        return Gatherer.<T, T>of(
                Gatherer.Integrator.<Void, T, T>of(
                        (unused, element, downstream) -> {
                            for (int i = 0; i < copies; i++) {
                                if (!downstream.push(element)) {
                                    return false;
                                }
                            }
                            return true;
                        }
                )
        );
    }

    public static void main(String[] args) {
        System.out.println(
                Stream.of("A", "B").gather(repeat(0)).toList()
        );

        System.out.println(
                Stream.of("A", "B").gather(repeat(1)).toList()
        );

        System.out.println(
                Stream.of("A", "B").gather(repeat(3)).toList()
        );
    }
}
~~~

Kết quả:

~~~text
[]
[A, B]
[A, A, A, B, B, B]
~~~

Giải thích:

- **repeat(0):** vòng lặp không chạy, integrator không gọi **push**. Mỗi đầu vào tạo ra 0 phần tử đầu ra, nhưng integrator vẫn trả về **true** để xử lý đầu vào tiếp theo.
- **repeat(1):** mỗi đầu vào gọi **push** một lần, tạo quan hệ one-to-one.
- **repeat(3):** mỗi đầu vào gọi **push** ba lần, tạo quan hệ one-to-many.
- Nếu downstream không còn nhận dữ liệu, **push** trả về **false**; integrator dừng vòng lặp và trả về **false** để ngừng tiêu thụ đầu vào.

Gatherer này không có trạng thái nên dùng overload **Gatherer.of(integrator)** với state type là **Void**. Đây là stateless Gatherer và factory method này hỗ trợ parallel evaluation.

## 4. Ví dụ thực tế: một dòng văn bản tạo ra nhiều từ

Một dòng văn bản có thể chứa không, một hoặc nhiều từ. Gatherer sau tách từng dòng thành các từ và phát từng từ qua downstream:

~~~java
import java.util.stream.Gatherer;
import java.util.stream.Stream;

class WordGatherer {
    static Gatherer<String, ?, String> words() {
        return Gatherer.<String, String>of(
                Gatherer.Integrator.<Void, String, String>of(
                        (unused, line, downstream) -> {
                            if (line.isBlank()) {
                                return true;
                            }

                            for (String word : line.strip().split("\\s+")) {
                                if (!downstream.push(word)) {
                                    return false;
                                }
                            }

                            return true;
                        }
                )
        );
    }

    public static void main(String[] args) {
        var result = Stream.of(
                    "Java 22",
                    "",
                    "Custom Gatherer"
                )
                .gather(words())
                .toList();

        System.out.println(result);
    }
}
~~~

Kết quả:

~~~text
[Java, 22, Custom, Gatherer]
~~~

Trong ví dụ:

- Dòng **"Java 22"** phát hai phần tử: **"Java"** và **"22"**.
- Dòng rỗng không gọi **push**, nên phát 0 phần tử.
- Dòng **"Custom Gatherer"** phát hai phần tử.
- Gatherer không giữ trạng thái giữa các dòng, vì mỗi dòng được xử lý độc lập.

Khi đầu vào có một từ, vòng lặp chỉ gọi **push** một lần. Vì vậy cùng một logic xử lý hỗ trợ cả 0, 1 và nhiều kết quả cho mỗi phần tử đầu vào.

Trong trường hợp chỉ cần tách chuỗi thành stream con, **flatMap** có thể là lựa chọn ngắn gọn hơn. Custom Gatherer hữu ích khi cần kết hợp việc phát nhiều kết quả với trạng thái, logic short-circuit hoặc quy tắc phát dữ liệu riêng.

## 5. Dừng phát khi downstream không cần thêm dữ liệu

Downstream có thể từ chối nhận thêm phần tử khi một operation phía sau đã đủ kết quả. Ví dụ, **limit(3)** chỉ cần ba phần tử đầu ra.

~~~java
import java.util.stream.Stream;

class WordLimitExample {
    public static void main(String[] args) {
        var result = Stream.of(
                    "one two three",
                    "four five"
                )
                .gather(WordGatherer.words())
                .limit(3)
                .toList();

        System.out.println(result);
    }
}
~~~

Kết quả:

~~~text
[one, two, three]
~~~

Khi downstream đã nhận đủ ba phần tử, lần gọi **push** tiếp theo có thể trả về **false**. Integrator trong WordGatherer kiểm tra kết quả đó, dừng vòng lặp và trả về **false**. Gatherer vì thế không tiếp tục tách những từ còn lại hoặc tiêu thụ thêm các dòng đầu vào.

Cách truyền tín hiệu này cho phép các operation short-circuit phía sau phối hợp với Gatherer. Nó đặc biệt hữu ích khi upstream là stream lớn hoặc vô hạn.

### isRejecting() để kiểm tra sớm

**downstream.isRejecting()** cho biết downstream đã được biết là không muốn nhận thêm dữ liệu hay chưa. Phương thức này có thể dùng để tránh công việc không cần thiết:

~~~java
if (downstream.isRejecting()) {
    return false;
}
~~~

Đây là kiểm tra best-effort. Nếu trả về **true**, downstream được biết là đã từ chối thêm dữ liệu. Nếu trả về **false**, điều đó không bảo đảm downstream sẽ tiếp tục chấp nhận mọi lần push sau. Vì vậy vẫn phải kiểm tra boolean trả về từ **push**.

## 6. Phát đầu ra trong finisher

Không phải mọi kết quả đều được phát ngay khi integrator nhận một phần tử. Với Gatherer có trạng thái, integrator có thể tích lũy dữ liệu rồi phát kết quả cuối cùng trong **finisher**.

Ví dụ sau gom đầu vào thành các lô có kích thước cố định. Khi đủ phần tử, integrator phát một batch. Khi upstream kết thúc, finisher phát batch cuối nếu còn phần tử chưa đủ kích thước.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Gatherer;

class BatchGatherer {
    static <T> Gatherer<T, ArrayList<T>, List<T>> batchesOf(int batchSize) {
        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize must be > 0");
        }

        return Gatherer.<T, ArrayList<T>, List<T>>ofSequential(
                ArrayList::new,

                Gatherer.Integrator.<ArrayList<T>, T, List<T>>of(
                        (state, element, downstream) -> {
                            state.add(element);

                            if (state.size() < batchSize) {
                                return true;
                            }

                            List<T> batch = new ArrayList<>(state);
                            state.clear();

                            return downstream.push(batch);
                        }
                ),

                (state, downstream) -> {
                    if (!state.isEmpty() && !downstream.isRejecting()) {
                        downstream.push(new ArrayList<>(state));
                    }
                }
        );
    }
}
~~~

Sử dụng:

~~~java
import java.util.stream.Stream;

class BatchExample {
    public static void main(String[] args) {
        var batches = Stream.of(1, 2, 3, 4, 5, 6, 7)
                .gather(BatchGatherer.batchesOf(3))
                .toList();

        System.out.println(batches);
    }
}
~~~

Kết quả:

~~~text
[[1, 2, 3], [4, 5, 6], [7]]
~~~

Trong Gatherer này:

- Các phần tử đầu tiên của một batch chỉ được lưu vào **state**, chưa phát đầu ra.
- Khi state đủ **batchSize**, integrator tạo bản sao của batch, xóa state và gọi **push** đúng một lần.
- Nếu đầu vào kết thúc khi batch chưa đủ, finisher phát phần còn lại qua **push**.
- **ofSequential(...)** được dùng vì ví dụ không cung cấp combiner; Gatherer này được đánh giá tuần tự.

Finisher cũng dùng cùng một **Downstream** và có thể phát không, một hoặc nhiều phần tử. Finisher không phải nơi để tiếp tục đọc upstream; nó chỉ xử lý trạng thái còn lại sau khi đầu vào đã kết thúc.

## 7. Tạo Gatherer bằng factory method

Không cần luôn tạo class riêng implements **Gatherer**. Interface cung cấp các factory method để định nghĩa Gatherer bằng lambda:

| Factory method | Trường hợp sử dụng |
|---|---|
| **Gatherer.of(integrator)** | Gatherer stateless; có thể chạy song song |
| **Gatherer.of(integrator, finisher)** | Stateless Gatherer có thao tác cuối luồng |
| **Gatherer.of(initializer, integrator, combiner, finisher)** | Stateful Gatherer có combiner để hỗ trợ parallel evaluation |
| **Gatherer.ofSequential(initializer, integrator)** | Stateful Gatherer chỉ chạy tuần tự |
| **Gatherer.ofSequential(initializer, integrator, finisher)** | Stateful Gatherer tuần tự có xử lý trạng thái cuối luồng |

**Integrator.of(...)** tạo integrator có thể chủ động short-circuit bằng cách trả về **false**. Nếu chắc chắn integrator luôn muốn tiêu thụ hết đầu vào và chỉ cần chuyển tiếp tín hiệu downstream từ **push**, có thể dùng **Integrator.ofGreedy(...)**. Không dùng greedy integrator cho logic cần tự dừng đầu vào theo điều kiện riêng.

## 8. Lưu ý về state, finisher và parallel evaluation

Một Gatherer được mô tả bằng ba kiểu:

- **T:** kiểu phần tử đầu vào.
- **A:** kiểu trạng thái trung gian do Gatherer quản lý.
- **R:** kiểu phần tử đầu ra.

Khi Gatherer có state, **initializer** tạo state mới cho một lần đánh giá hoặc một partition. Không dùng chung một mutable state giữa các lần xử lý độc lập.

Khi chạy song song, **combiner** hợp nhất hai state trung gian. Chỉ cung cấp combiner khi có thể kết hợp đúng kết quả của hai partition theo ngữ nghĩa Gatherer. Nếu không thể xác định cách hợp nhất đúng, dùng **ofSequential(...)**.

Các quy tắc quan trọng:

- State được truyền cho integrator, combiner và finisher phải do initializer hoặc combiner tạo ra.
- Sau khi state được chuyển cho combiner hoặc finisher, không sử dụng lại state đó trong integrator.
- Không giữ reference đến state hoặc **Downstream** lâu hơn thời gian thực thi phương thức nhận chúng.
- Nếu integrator trả về **false**, việc tiêu thụ đầu vào dừng tại đó; các phần xử lý phía sau không được giả định sẽ nhận đủ dữ liệu như khi chạy hết stream.
- Finisher có thể phát đầu ra cuối luồng, nhưng nếu downstream đã short-circuit thì đầu ra cuối đó có thể không được chuyển tiếp.

Với Gatherer phát nhiều phần tử, cần đặc biệt chú ý thứ tự. Nếu một input tạo ra nhiều output, hãy phát chúng theo đúng thứ tự mong muốn trước khi chuyển sang input tiếp theo. Khi dùng parallel evaluation, combiner phải bảo toàn ngữ nghĩa và encounter order mà ứng dụng yêu cầu.

## 9. Khi nào nên dùng Downstream.push?

| Nhu cầu | Cách triển khai |
|---|---|
| Bỏ qua một số input | Không gọi **push**, trả về **true** để đọc input tiếp theo |
| Chuyển mỗi input thành một output | Gọi **push** một lần |
| Một input tạo nhiều output | Gọi **push** trong vòng lặp; dừng nếu nhận **false** |
| Gom nhiều input rồi mới phát output | Lưu vào state, phát bằng **push** khi đủ điều kiện |
| Phát dữ liệu còn lại khi upstream kết thúc | Dùng finisher và **push** |
| Dừng khi downstream không cần thêm | Kiểm tra kết quả **push** và trả về **false** từ integrator |
| Không có combiner đúng cho state | Chọn **Gatherer.ofSequential(...)** |

Custom Gatherer phù hợp khi cần một phép biến đổi trung gian có trạng thái hoặc phát số lượng đầu ra khác nhau cho từng đầu vào. Nếu chỉ cần phép toán phổ biến, hãy ưu tiên các operation có sẵn như **map**, **filter**, **flatMap** hoặc **Gatherers**. API tiêu chuẩn dễ đọc hơn và tránh phải tự quản lý những quy tắc của Gatherer.

## Tài liệu tham khảo chính thức

- [JEP 461 — Stream Gatherers (Preview)](https://openjdk.org/jeps/461): lần preview đầu tiên trong JDK 22.
- [JEP 473 — Stream Gatherers (Second Preview)](https://openjdk.org/jeps/473): vòng preview tiếp theo trong JDK 23.
- [JEP 485 — Stream Gatherers](https://openjdk.org/jeps/485): hoàn thiện API trong JDK 24.
- [Gatherer — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.html): state, integrator, combiner, finisher và factory methods.
- [Gatherer.Integrator — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.Integrator.html): semantics của integrate và Integrator.of/ofGreedy.
- [Gatherer.Downstream — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.Downstream.html): push, giá trị trả về và isRejecting.
- [Stream Gatherers — Java 24 Core Libraries Guide](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html): ví dụ custom Gatherer và cách phối hợp các thành phần.

