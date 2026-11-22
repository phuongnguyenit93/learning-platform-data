# Vai trò của Java 5 trong nền tảng ngôn ngữ và thư viện Java

## 1. Học Java 5 để hiểu Java đang viết hôm nay

Java 5 là một cột mốc hình thành nhiều cách viết Java vẫn xuất hiện trong ứng dụng hiện đại. Khi đọc `List<String>`, một enum trạng thái, annotation trên lớp hoặc `ExecutorService` thực thi tác vụ, người học đang sử dụng những nền tảng được đưa vào hoặc được định hình mạnh ở giai đoạn này.

Giá trị của việc học nằm ở **các khái niệm còn hiện hành**, không phải ở việc quay lại môi trường chạy cũ. Bài sử dụng JDK hiện đại và ví dụ Java 17+ để quan sát những nền tảng đó.

Có thể nhìn đóng góp của Java 5 qua ba hướng:

| Hướng | Vấn đề được giải quyết | Dấu vết trong Java hiện đại |
| --- | --- | --- |
| Hợp đồng kiểu rõ hơn | Phát hiện truyền và lấy dữ liệu sai kiểu sớm hơn | Generics, enum |
| Biểu đạt ý định gọn hơn | Giảm mã lặp nhưng giữ mô hình có kiểu | Enhanced for, autoboxing, varargs, static import |
| Cơ chế và thư viện dùng lại | Có mô hình chuẩn cho metadata và thực thi đồng thời | Annotation, `java.util.concurrent`, mô hình bộ nhớ |

Không phải mọi tính năng hiện đại đều có từ Java 5. Lambda, Stream, record, suy luận kiểu biến cục bộ và virtual thread thuộc những bước phát triển sau. Hiểu nền tảng giúp thấy cách chúng kết hợp, thay vì gom tất cả thành một “phong cách Java mới” không có ranh giới khái niệm.

## 2. Java 5 là một lớp nền, không phải toàn bộ nền tảng Java

Ngôn ngữ và thư viện có trách nhiệm khác nhau:

- **Ngôn ngữ** định nghĩa cú pháp và quy tắc như tham số kiểu, enum, annotation, boxing hoặc vòng lặp mở rộng.
- **Trình biên dịch** kiểm tra và chuyển mã nguồn theo các quy tắc đó.
- **JVM** thực thi mã lớp và tuân thủ mô hình thực thi/bộ nhớ.
- **Thư viện** cung cấp các lớp và hợp đồng như `List`, `Callable`, `Future` và `ExecutorService`.

Ví dụ `List<String>` không chỉ là một chuỗi có dấu ngoặc nhọn góc. Nó kết hợp cơ chế generics của ngôn ngữ với thiết kế tham số kiểu của thư viện Collection.

Tương tự, annotation có cú pháp chuẩn nhưng tác dụng còn phụ thuộc bên đọc nó. Một annotation của công cụ kiểm tra, một annotation được framework đọc lúc chạy và `@Override` không cùng hoạt động theo một cách duy nhất.

Bản tổng hợp [các cải tiến ngôn ngữ của Oracle](https://docs.oracle.com/javase/8/docs/technotes/guides/language/enhancements.html) đặt generics, enhanced for, boxing, enum, varargs và static import trong mốc Java 5. Điều còn quan trọng ở hiện tại là nắm hợp đồng sử dụng của từng cơ chế trong mã đang viết.

## 3. Generics: nền tảng của API có kiểu

### 3.1. Hợp đồng kiểu đi cùng dữ liệu

`List<String>` nói rằng danh sách được sử dụng với phần tử kiểu `String`. Khi lấy phần tử qua API đúng kiểu, trình biên dịch biết kết quả là `String`.

```java
List<String> names = new ArrayList<>();
names.add("An");

String firstName = names.get(0);
// names.add(42); // Khong bien dich: int khong phu hop voi String.
```

Đoạn minh họa cần import `java.util.List` và `java.util.ArrayList`. Diamond `<>` ở vế tạo đối tượng là cú pháp bổ sung sau Java 5; nền tảng ở đây là việc tham số hóa `List` bằng kiểu phần tử.

Vai trò lớn hơn của generics không chỉ là bỏ một phép ép kiểu. Nó cho phép API diễn tả mối liên hệ:

- `List<T>` lưu và trả phần tử theo `T`.
- `Map<K, V>` liên hệ khóa với giá trị.
- `Callable<V>` mô tả tác vụ trả `V`.
- `Future<V>` mô tả kết quả có thể lấy được dưới kiểu `V`.
- Một phương thức `<T>` có thể giữ quan hệ kiểu giữa tham số đầu vào và kết quả.

Trong Java hiện đại, `Optional<T>`, `Stream<T>` hoặc nhiều API framework tiếp tục dựa trên cùng nền tảng tham số kiểu. Chúng không làm generics trở nên thừa; chúng dùng generics để công bố hợp đồng của chính mình.

### 3.2. An toàn kiểu không có nghĩa mọi lỗi biến mất

[Đặc tả kiểu của Java hiện hành](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html) vẫn mô tả tham số kiểu và cơ chế xóa kiểu. Người học cần nhận ra một số giới hạn còn áp dụng:

- `List<Integer>` không phải kiểu con của `List<Number>`.
- Không dùng trực tiếp kiểu nguyên thủy như `List<int>`; phải dùng kiểu tham chiếu thích hợp.
- Một số thông tin kiểu tổng quát không được biểu diễn đầy đủ ở thời điểm chạy như trong mã nguồn.
- Ép kiểu không được kiểm tra hoặc dữ liệu vi phạm hợp đồng có thể làm mất bảo đảm ban đầu.

Không giải quyết một lỗi kiểu bằng cách chuyển API mới sang raw type rồi bỏ qua cảnh báo. Đối với mã được thiết kế mới, hãy giữ tham số kiểu và tìm đúng quan hệ giữa đầu vào/đầu ra. Wildcard và giới hạn kiểu là công cụ để biểu đạt quan hệ đó, không chỉ là cú pháp để làm trình biên dịch im lặng.

Trong phạm vi bài tổng quan, điều cần đạt là đọc được chữ ký và hiểu generics bảo vệ điều gì. Các quy tắc chi tiết của wildcard và xóa kiểu nên được học theo một chủ đề chuyên sâu.

## 4. Enum: mô hình hóa một tập lựa chọn hữu hạn

Một trạng thái công việc có thể là `NEW` hoặc `COMPLETED`:

```java
enum RunState {
    NEW, COMPLETED
}
```

Tham số kiểu `RunState` rõ hơn một `int` hoặc `String` không có ràng buộc. Người gọi không thể truyền tùy tiện `"DONEE"` vào tham số yêu cầu `RunState` mà không qua một bước chuyển đổi có kiểm tra.

Enum trong Java còn có thể có trường và phương thức. Vì vậy, nó phù hợp cho những tập lựa chọn có ý nghĩa và hành vi liên quan, không chỉ là một nhóm số.

Trong thư viện hiện hành, `DayOfWeek`, `Month` và `TimeUnit` là các ví dụ dễ nhận thấy của cách mô hình này. Những API đó giúp mã đọc được ý nghĩa trực tiếp thay vì dựa vào các số khó nhớ.

Cần giữ những ranh giới:

- Enum phù hợp với tập giá trị được định nghĩa trong mã; không nhất thiết phù hợp với danh mục do người dùng thêm tùy ý lúc chạy.
- `ordinal()` là vị trí khai báo, không phải mã nghiệp vụ bền vững để lưu trao đổi.
- Nếu cần mã dữ liệu ổn định, hãy có một hợp đồng mã rõ ràng thay vì phụ thuộc vào thứ tự enum.
- Thêm một hằng mới có thể yêu cầu xem lại các nhánh xử lý, ánh xạ hoặc giao thức; an toàn kiểu không tự quyết định nghiệp vụ cho giá trị mới.

Bài dùng enum trạng thái để thể hiện vai trò kiểu. Nó không biến hai hằng `NEW`/`COMPLETED` thành một hệ thống quản lý chuyển trạng thái hoàn chỉnh.

## 5. Annotation: metadata có bên diễn giải

Annotation là dữ liệu mô tả được gắn vào các vị trí hợp lệ của chương trình. Nó có thể được trình biên dịch, công cụ hoặc mã lúc chạy đọc và xử lý.

[Đặc tả annotation trong Java](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6) vẫn là một phần của ngôn ngữ hiện hành. Các câu hỏi phải làm rõ khi gặp một annotation là:

1. Nó được phép gắn ở đâu?
2. Nó tồn tại đến giai đoạn nào?
3. Ai đọc nó?
4. Bên đọc làm gì với giá trị được khai báo?

Ví dụ `@Override` giúp trình biên dịch kiểm tra ý định ghi đè/thực hiện phương thức theo quy tắc hiện hành. Một annotation tự viết với `RetentionPolicy.RUNTIME` có thể được đọc qua reflection, nhưng **không tự sinh hành vi** nếu không có bên đọc.

Chương trình bên dưới khai báo `@LearningTopic` và chủ động gọi `getAnnotation` để lấy tên chủ đề. Nếu bỏ lời gọi đọc, annotation đó không tự in thông báo hoặc thay cách các tác vụ thực thi.

Hiểu điều này hữu ích khi học framework: annotation cấu hình không phải một “lệnh ma thuật” tự có hiệu lực chỉ vì bắt đầu bằng `@`. Phải có cơ chế của framework, công cụ biên dịch hoặc thành phần tương ứng nhận diện nó.

Cũng cần phân biệt các phần mở rộng sau này, như annotation trên vị trí sử dụng kiểu hoặc annotation lặp lại, với nền tảng annotation ban đầu. Bài chỉ dùng cơ chế còn áp dụng và không yêu cầu công cụ xử lý annotation cũ.

## 6. Các tiện ích cú pháp giảm lặp nhưng không bỏ quy tắc

### 6.1. Enhanced for thể hiện ý định duyệt

```java
for (String name : names) {
    System.out.println(name);
}
```

Vòng lặp mở rộng phù hợp khi cần xử lý từng phần tử của mảng hoặc đối tượng `Iterable` và không cần chỉ số.

Nó không làm mọi tập hợp an toàn khi bị sửa trong lúc duyệt và cũng không biến xử lý thành song song. Nếu cần vị trí, cập nhật theo chỉ số hoặc loại phần tử bằng cơ chế duyệt phù hợp, hãy chọn cấu trúc khác theo hợp đồng của tập hợp.

Stream không làm vòng lặp này lỗi thời. Một vòng lặp có thể là cách rõ nhất cho thao tác tuần tự ngắn, còn Stream phù hợp khi mô hình xử lý dữ liệu và tính kết hợp của các bước đem lại lợi ích cụ thể.

### 6.2. Autoboxing/unboxing nối kiểu nguyên thủy và wrapper

`Integer` có thể được tạo tự động từ `int` khi cần một đối tượng; một `Integer` có thể được mở hộp thành `int` khi tham gia phép tính thích hợp.

Trong ví dụ, `Callable<Integer>` trả về một biến `int` qua boxing; kết quả `Integer` được cộng vào `int total` qua unboxing.

Các điểm cần giữ:

- Wrapper có thể là `null`; mở hộp `null` gây `NullPointerException`.
- `==` giữa hai tham chiếu wrapper có thể so danh tính đối tượng, không phải điều người viết muốn khi so giá trị.
- Boxing không miễn phí về thiết kế và có thể có chi phí; với xử lý số lượng lớn, cần chọn cấu trúc phù hợp.
- Tự động chuyển đổi không có nghĩa kiểu nguyên thủy và kiểu tham chiếu đã trở thành cùng một kiểu.

Các giới hạn này vẫn xuất hiện trong collection, API có kiểu tổng quát và mã hiện đại. Không nên chỉ học boxing như một cách viết ngắn hơn rồi bỏ qua ngữ nghĩa.

### 6.3. Varargs cho số đối số thay đổi

```java
SumTask(int... values)
```

cho phép gọi `new SumTask(1, 2, 3)`. Bên trong, `values` là một mảng `int[]`.

Đây là cơ chế gọi hàm thuận tiện, không phải một danh sách tự tăng kích thước hoặc một API vô hạn tài nguyên. Khi người gọi đưa một mảng có sẵn vào, hiện thực cần quyết định có giữ tham chiếu và cho phép thay đổi ngoài ý muốn hay không.

`SumTask` trong chương trình sao chép mảng bằng `clone`. Nhờ đó, nội dung tác vụ không bị thay đổi nếu nơi tạo tác vụ sửa mảng đầu vào sau này.

Varargs kết hợp với tham số kiểu có các rủi ro riêng về mảng và thông tin kiểu. Không áp dụng các annotation bỏ cảnh báo một cách máy móc; đó là phần cần xét riêng khi thiết kế API generic varargs.

### 6.4. Static import giúp đọc mã khi dùng có chọn lọc

```java
import static java.util.concurrent.TimeUnit.SECONDS;
```

cho phép viết `future.get(5, SECONDS)`. Tên đơn vị vẫn dễ thấy ở lời gọi.

Static import không làm giá trị đó thành biến cục bộ hoặc thay cơ chế liên kết kiểu. Nếu nhập quá nhiều thành viên có tên chung như `get`, `max` hoặc `value` từ nhiều lớp, mã có thể khó truy nguồn hơn. Chỉ dùng khi sự ngắn gọn giúp người đọc, không phải để xóa mọi tên lớp khỏi mã.

## 7. Thư viện đồng thời: tác vụ và quản lý thực thi

Java 5 đánh dấu việc đưa nhiều công cụ đồng thời cấp cao vào thư viện chuẩn. [java.util.concurrent hiện hành](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html) tiếp tục cung cấp các hợp đồng cốt lõi:

| Thành phần | Vai trò |
| --- | --- |
| `Executor` | Nhận công việc để thực thi |
| `ExecutorService` | Quản lý gửi tác vụ và vòng đời dịch vụ thực thi |
| `Callable<V>` | Tác vụ có kết quả kiểu `V` và có thể báo lỗi |
| `Future<V>` | Đại diện kết quả của một tác vụ đã gửi |
| `BlockingQueue` | Hàng đợi phối hợp theo hợp đồng chờ phù hợp |
| `ConcurrentHashMap` | Bản đồ có các thao tác được thiết kế cho truy cập đồng thời |
| Các lớp atomic và lock | Cơ chế cập nhật/phối hợp có bảo đảm riêng |

Vai trò của lớp nền này là tách câu hỏi “tác vụ làm gì?” khỏi “ai thực thi, quản lý và lấy kết quả thế nào?”.

Tuy vậy, dùng một collection concurrent không làm mọi chuỗi thao tác nghiệp vụ tự trở nên nguyên tử. Dùng `Future` cũng không làm chờ kết quả hết tốn thời gian. Cần hiểu hợp đồng của thao tác cụ thể, xử lý lỗi, ngắt và vòng đời tài nguyên.

Các mô hình mới hơn như `CompletableFuture` hoặc virtual thread bổ sung lựa chọn, nhưng không xóa các câu hỏi về kết quả, hủy, chia sẻ trạng thái và giới hạn tài nguyên. Chúng phải được học theo đúng cơ chế riêng, không được coi là có sẵn từ Java 5.

## 8. Mô hình bộ nhớ: nền của suy luận đồng thời

Một chương trình nhiều luồng phải trả lời không chỉ “ai chạy trước” mà còn “một luồng được bảo đảm nhìn thấy cập nhật nào của luồng khác”.

[Mô hình bộ nhớ Java hiện hành](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html) quy định các quan hệ bảo đảm như happens-before. Đây là lớp nền cho việc hiểu `synchronized`, `volatile`, trường `final` và các công cụ đồng thời chuẩn.

Một số phân biệt vẫn quan trọng:

- Khả năng nhìn thấy cập nhật không đồng nhất với tính nguyên tử của một chuỗi thao tác.
- `volatile` không tự làm `count++` thành một thao tác nguyên tử.
- `final` trên một tham chiếu không làm toàn bộ đối tượng được tham chiếu trở thành bất biến.
- Dùng thư viện đồng thời đúng hợp đồng thường giúp diễn đạt bảo đảm rõ hơn tự suy luận từ tốc độ hoặc thứ tự in ra màn hình.

Bài không trình bày lại toàn bộ mô hình bộ nhớ. Vai trò cần nhận ra là các tính năng thư viện hiện đại dựa vào bảo đảm thực thi có quy định, không dựa vào giả định “chạy trên máy tôi luôn như vậy”.

## 9. Chương trình Java 17+ kết nối các nền tảng

Lưu thành `Java5FoundationDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static java.util.concurrent.TimeUnit.SECONDS;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface LearningTopic {
    String value();
}

@LearningTopic("type-safe tasks")
public class Java5FoundationDemo {
    enum RunState {
        NEW, COMPLETED
    }

    static final class SumTask implements Callable<Integer> {
        private final int[] values;

        SumTask(int... values) {
            this.values = values.clone();
        }

        @Override
        public Integer call() {
            int total = 0;
            for (int value : values) {
                total += value;
            }
            return total;
        }
    }

    static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("Empty list");
        }
        return values.get(0);
    }

    public static void main(String[] args) throws Exception {
        List<Callable<Integer>> tasks = List.of(
                new SumTask(1, 2, 3),
                new SumTask(4, 5));

        LearningTopic topic = Java5FoundationDemo.class
                .getAnnotation(LearningTopic.class);
        System.out.println("annotation = " + topic.value());
        System.out.println("task count = " + tasks.size());

        RunState state = RunState.NEW;
        System.out.println("before = " + state);

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            List<Future<Integer>> futures = new ArrayList<>();
            for (Callable<Integer> task : tasks) {
                futures.add(executor.submit(task));
            }

            List<Integer> results = new ArrayList<>();
            int total = 0;
            for (Future<Integer> future : futures) {
                Integer result = future.get(5, SECONDS);
                results.add(result);
                total += result;
            }

            state = RunState.COMPLETED;
            System.out.println("results = " + results);
            System.out.println("first result = " + first(results));
            System.out.println("total = " + total);
            System.out.println("after = " + state);
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:unchecked Java5FoundationDemo.java
java Java5FoundationDemo
```

Stdout:

```text
annotation = type-safe tasks
task count = 2
before = NEW
results = [6, 9]
first result = 6
total = 15
after = COMPLETED
```

Mã được kiểm chứng trên JDK hiện đại. Nó không được viết để chạy trên JDK 5: `List.of` và diamond là các tiện ích được bổ sung sau. Chúng được dùng để trình bày ngắn gọn trong ngữ cảnh hiện nay, còn những quan hệ kiểu và cơ chế chính là chủ đề của bài.

### 9.1. Các phần phối hợp thế nào?

1. `LearningTopic` gắn metadata vào lớp; `getAnnotation` là bên đọc cụ thể.
2. `RunState` biểu diễn trạng thái bằng enum.
3. `SumTask` nhận varargs, giữ bản sao của mảng và thực hiện một `Callable<Integer>`.
4. Enhanced for duyệt các số và các tác vụ.
5. `List<Callable<Integer>>` và `List<Future<Integer>>` giữ hợp đồng kiểu trên đường gửi và lấy kết quả.
6. `Future.get` trả `Integer`; boxing/unboxing nối kết quả đó với phép cộng số nguyên.
7. Static import giúp nêu đơn vị `SECONDS` trong lời gọi có giới hạn chờ.

Kết quả được lấy theo thứ tự danh sách `futures`, là thứ tự gửi tác vụ trong ví dụ. Điều đó không chứng minh các luồng đã hoàn thành theo thứ tự đó. Chương trình không in từ các tác vụ nên stdout không phụ thuộc thứ tự xen kẽ của hai luồng.

### 9.2. Vòng đời thực thi và phạm vi ví dụ

Ví dụ chỉ gửi hai tác vụ nhỏ đã biết trước. `finally` yêu cầu dừng dịch vụ thực thi dù đường xử lý thành công hay báo lỗi.

Thời hạn `5` giây áp dụng cho mỗi lần gọi `get`, không phải một thời hạn chung cho toàn bộ chương trình. Đây không phải bảo đảm thời gian thực.

`newFixedThreadPool` trong ví dụ không phải đề xuất chung cho một dịch vụ nhận lượng công việc không giới hạn. Trong hệ thống thật, cần thiết kế giới hạn hàng chờ, tải, chính sách từ chối, hủy và dừng tài nguyên theo nhu cầu. `shutdownNow` là yêu cầu ngắt/dừng theo hợp đồng, không ép một tác vụ bất kỳ chắc chắn dừng tức thì.

Mẫu nhỏ giúp thấy các nền tảng phối hợp, không thay thế một thiết kế hệ thống thực thi tác vụ hoàn chỉnh.

## 10. Phân biệt nền tảng với bổ sung về sau

| Thành phần gặp trong mã hiện đại | Nền tảng liên quan | Điều không nên suy nhầm |
| --- | --- | --- |
| `List<String>` | Generics | Diamond không phải cú pháp gốc của Java 5 |
| Một lambda truyền cho tác vụ | Giao diện tác vụ + cơ chế hàm của phiên bản sau | Lambda không có từ Java 5 |
| `Stream<T>` | Generics và mô hình xử lý dữ liệu về sau | Stream không thay thế toàn bộ vòng lặp |
| Annotation framework | Metadata và bên xử lý | Không phải annotation nào cũng tự có tác dụng |
| Record chứa enum và danh sách | Cơ chế record về sau kết hợp các kiểu nền | Record không phải thành phần của Java 5 |
| Virtual thread gửi công việc qua API thực thi | Công cụ thực thi mới kết hợp hợp đồng tác vụ | Không phải mọi vấn đề đồng thời đã biến mất |
| `var` suy luận một kiểu generic | Suy luận kiểu biến cục bộ về sau | `var` không làm Java trở thành ngôn ngữ không có kiểu |

Học theo cách này tránh hai thái cực: coi mọi tính năng cũ đều không còn giá trị hoặc coi mọi công cụ hiện đại đã có nguyên vẹn từ Java 5.

Một tính năng có lịch sử lâu không tự trở thành lỗi thời. Tiêu chí dùng là hợp đồng hiện hành, mức phù hợp của mô hình và cách viết đúng trong môi trường đang triển khai.

## 11. Cách áp dụng vào việc học và đọc dự án

Có thể theo thứ tự:

1. Đọc generics trong chữ ký thư viện: đầu vào nào liên quan đến kiểu kết quả nào?
2. Nhận diện enum đang mô hình hóa tập lựa chọn gì.
3. Với annotation, tìm bên đọc hoặc kiểm tra nó.
4. Đọc enhanced for, boxing và varargs như các cơ chế có quy tắc cụ thể.
5. Xem tác vụ được gửi đi đâu, kết quả/lỗi được lấy ở đâu và ai chịu trách nhiệm dừng dịch vụ thực thi.
6. Khi có trạng thái chia sẻ, tìm bảo đảm đồng bộ thay vì dựa vào thứ tự quan sát tình cờ.

Không cần viết một framework nhỏ để chứng minh đã hiểu annotation, cũng không cần đưa đa luồng vào mọi ví dụ generics. Hãy chọn vấn đề phù hợp rồi dùng cơ chế tương ứng.

Trong một lần đọc mã, nếu nhìn thấy cảnh báo kiểu bị bỏ qua, wrapper có thể `null` hoặc executor không có chủ sở hữu vòng đời rõ, đó là những điểm cần điều tra về hợp đồng hiện tại. Chúng không được giải quyết chỉ bằng việc dự án dùng một JDK mới hơn.

## 12. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu phù hợp |
| --- | --- |
| Học Java 5 nghĩa là phải dùng môi trường chạy cũ | Có thể học các nền tảng còn hiện hành trên JDK hiện đại |
| Generics chỉ để không cần ép kiểu | Nó diễn tả quan hệ kiểu của API |
| Enum chỉ là nhóm số nguyên | Nó là một kiểu có tập hằng và có thể có hành vi |
| Annotation luôn tự chạy một chức năng | Phải có bên diễn giải theo hợp đồng |
| Enhanced for luôn tốt hơn mọi vòng lặp | Nó phù hợp khi cần duyệt từng phần tử mà không cần chỉ số đặc biệt |
| Boxing làm nguyên thủy và wrapper giống hệt nhau | Vẫn có khác biệt về `null`, danh tính và chi phí |
| Varargs là một danh sách linh hoạt | Tham số được xử lý như mảng |
| Concurrent collection làm mọi quy trình nguyên tử | Chỉ các bảo đảm được công bố của thao tác mới áp dụng |
| JDK mới khiến không cần hiểu mô hình bộ nhớ | Mã chia sẻ trạng thái vẫn cần bảo đảm đồng bộ |
| Lambda, Stream và record đều có từ Java 5 | Chúng là các bổ sung khác, dùng cùng nhiều nền tảng trước đó |

## 13. Tự kiểm chứng và thực hành

1. Trong ví dụ, chỉ ra các quan hệ kiểu từ `Callable<Integer>` đến `Future<Integer>` và `List<Integer>`. Nếu đổi kết quả tác vụ thành `String`, những chữ ký nào phải thay?
2. Viết một đoạn cố thêm sai kiểu vào `List<String>` và quan sát lỗi biên dịch. Không dùng ép kiểu không được kiểm tra để làm nó qua.
3. Thêm một trạng thái enum và xem những nơi nào thực sự cần xử lý giá trị mới. Phân biệt có một hằng với đã thiết kế xong luồng chuyển trạng thái.
4. Bỏ dòng đọc `LearningTopic` trong ví dụ. Giải thích vì sao annotation vẫn có thể tồn tại nhưng không tự in kết quả.
5. Thay một kết quả `Integer` bằng `null` trong một thí nghiệm riêng. Xác định điểm unboxing có thể gây lỗi, rồi chọn hợp đồng dữ liệu phù hợp.
6. Tạo một mảng `int[]` rồi truyền vào `SumTask`; sửa mảng gốc trước khi chạy. Giải thích vai trò của bản sao trong constructor.
7. Cho hai tác vụ có thời gian hoàn thành khác nhau nhưng vẫn lấy `Future` theo thứ tự gửi. Phân biệt thứ tự lấy kết quả với thứ tự hoàn thành.
8. Tìm một API hiện đại có kiểu `<T>` hoặc annotation và mô tả lớp nền nào giúp nó biểu đạt hợp đồng.
9. Với một đoạn mã dùng `volatile int count` và `count++` từ nhiều luồng, giải thích vì sao từ khóa `volatile` chưa đủ cho tính nguyên tử.
10. Đánh dấu trong chương trình phần nào bắt nguồn từ các nền tảng Java 5 và phần tiện ích nào được bổ sung về sau. Không cần sửa mã thành phong cách của môi trường cũ.

Nắm vai trò của Java 5 giúp người học đọc Java hiện đại theo các cơ chế có quan hệ: kiểu dữ liệu bảo vệ hợp đồng, cú pháp giảm lặp, metadata cần bên xử lý và thư viện đồng thời dựa trên bảo đảm thực thi. Những nền tảng này tiếp tục hữu ích khi làm việc trên các phiên bản Java hiện nay.
