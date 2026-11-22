# Runnable, Callable và Comparator như kiểu đích của lambda trong Java

## Mục tiêu học tập

Khi đọc một lambda như \`() -> ...\` hoặc \`(a, b) -> ...\`, chỉ nhìn vào dấu mũi tên chưa đủ để biết tham số, kết quả hay ngoại lệ hợp lệ. **Kiểu đích (target type)**, cụ thể là một **giao diện hàm (functional interface)**, mới quyết định hợp đồng mà lambda phải thực hiện.

Bài này dùng ba giao diện phổ biến, vẫn được dùng rộng rãi trong Java hiện đại: \`Runnable\`, \`Callable<V>\` và \`Comparator<T>\`. Sau khi học, bạn sẽ:

- Nhận diện phương thức trừu tượng duy nhất của từng giao diện và suy luận chữ ký tương ứng cho lambda.
- Phân biệt một tác vụ không trả kết quả với tác vụ trả kết quả, cũng như một hành vi so sánh hai giá trị.
- Hiểu sự khác nhau giữa **gọi trực tiếp** phương thức chức năng và **gửi tác vụ cho executor**.
- Dùng \`Comparator\` để sắp xếp đúng quy tắc, tránh phép trừ có thể tràn số và các bộ so sánh không nhất quán.
- Đọc lỗi biên dịch liên quan đến số tham số, kiểu trả về, checked exception, suy luận kiểu và ngữ cảnh thiếu kiểu đích.

Các ví dụ hoàn chỉnh chỉ dùng API có từ Java 8, nên cũng chạy trên JDK 17, 21 và các JDK mới hơn. Những công cụ bổ sung trên JDK mới không làm thay đổi nguyên tắc kiểu đích được giải thích ở đây.

## 1. Lambda luôn được hiểu trong một ngữ cảnh kiểu

Một biểu thức lambda mô tả cách triển khai phương thức trừu tượng của giao diện hàm. Nó không tự mang một kiểu hàm độc lập như \`(int) -> String\` có thể đứng một mình trong cú pháp khai báo Java.

Cùng một biểu thức có thể phù hợp nhiều giao diện hàm, tùy **kiểu đích**:

~~~java
Runnable first = () -> System.out.println("Chạy");
java.util.concurrent.Callable<String> second = () -> "Kết quả";
~~~

Đây là hai đoạn minh họa để đặt bên trong phương thức hoặc lớp phù hợp; không phải chương trình độc lập. Cả hai cùng có **0 tham số**, nhưng \`Runnable\` yêu cầu kết quả \`void\`, còn \`Callable<String>\` yêu cầu kết quả \`String\`.

Thông tin kiểu đích thường xuất hiện ở:

1. **Vế trái phép gán hoặc khai báo:** \`Runnable task = () -> ...;\`
2. **Tham số phương thức:** \`executor.execute(() -> ...);\` với \`execute(Runnable)\`.
3. **Ngữ cảnh trả về:** phương thức khai báo trả về \`Comparator<String>\` có thể \`return (a, b) -> ...;\`.
4. **Phép ép kiểu rõ ràng:** \`(Runnable) () -> ...\` giúp chỉ định đích khi cần làm rõ.

Do đó, cách đọc đúng là: **xác định giao diện đích → tìm phương thức trừu tượng duy nhất (SAM) → đối chiếu số tham số, kiểu tham số, kiểu trả về và ngoại lệ được phép ném**.

Đặt \`@FunctionalInterface\` lên một giao diện do bạn định nghĩa sẽ khiến trình biên dịch kiểm tra hợp đồng SAM. Annotation này không bắt buộc đối với những giao diện vốn đã là functional interface, nhưng hữu ích khi thiết kế API.

## 2. Ba hợp đồng cần nhớ

| Giao diện | Phương thức trừu tượng cần triển khai | Số tham số lambda | Kết quả | Checked exception |
| --- | --- | ---: | --- | --- |
| \`java.lang.Runnable\` | \`void run()\` | 0 | \`void\` | \`run()\` không khai báo \`throws\` |
| \`java.util.concurrent.Callable<V>\` | \`V call() throws Exception\` | 0 | Giá trị kiểu \`V\` | \`call()\` được phép ném checked exception phù hợp |
| \`java.util.Comparator<T>\` | \`int compare(T a, T b)\` | 2 | Số nguyên thể hiện thứ tự | \`compare()\` không khai báo checked exception |

**Runnable** mô tả một hành động có thể chạy; **Callable** mô tả một phép xử lý trả kết quả và có thể báo lỗi; **Comparator** mô tả quy tắc xác định thứ tự hai đối tượng. Dù đều là giao diện hàm, chúng không hoán đổi cho nhau vì **chữ ký SAM khác nhau**.

Với \`Callable<Integer>\`, kiểu \`V\` là \`Integer\`. Trình biên dịch chấp nhận biểu thức tính ra \`int\` khi kết quả có thể được boxing thành \`Integer\`. Với \`Comparator<String>\`, hai tham số có kiểu \`String\`, và lambda cần tạo ra \`int\` diễn tả quan hệ thứ tự.

\`Comparator\` cũng định nghĩa các phương thức \`default\` và \`static\` để kết hợp bộ so sánh. Các phương thức đó **không làm mất tính chất functional interface**. Các phương thức tương ứng với những phương thức \`public\` của \`Object\` cũng không được tính thêm như SAM độc lập.

## 3. Runnable là kiểu đích cho lambda không tham số, không có kết quả

Phương thức \`Runnable.run()\` nhận 0 đối số và trả về \`void\`. Vì thế, lambda thường có dạng:

~~~java
Runnable log = () -> System.out.println("Bắt đầu");
Runnable multiLine = () -> {
    System.out.println("Bước 1");
    System.out.println("Bước 2");
};
~~~

Đoạn này minh họa cách khai báo trong phương thức. Với dạng khối, các câu lệnh nằm trong \`{ }\`; không trả về giá trị.

**Một việc rất dễ nhầm:** tạo \`Runnable\` không có nghĩa là tác vụ đã chạy, càng không có nghĩa JVM tự khởi tạo luồng. Chỉ khi ai đó gọi \`run()\`, hoặc một API như \`Thread\` hay \`Executor\` gọi \`run()\`, phần thân mới thực thi.

~~~java
Runnable task = () -> System.out.println("Đã thực hiện");
task.run(); // Gọi trực tiếp trên luồng hiện tại.
~~~

\`task.run()\` là lời gọi phương thức bình thường, thực thi trên **luồng hiện tại**. Nếu muốn giao việc cho bộ thực thi, có thể dùng \`executor.execute(task)\` hoặc \`executor.submit(task)\` tùy API và yêu cầu lấy trạng thái hoàn thành.

Vì \`Runnable.run()\` không khai báo checked exception, lambda gán cho \`Runnable\` không thể ném thẳng checked exception chưa được xử lý như \`IOException\`. Cần xử lý ngay bên trong, hoặc dùng một API/giao diện phù hợp cho công việc có thể ném lỗi đã kiểm tra.

Ví dụ đoạn sau **không biên dịch**:

~~~java
// Runnable invalid = () -> { throw new java.io.IOException("I/O"); };
~~~

Đây là dòng lỗi được đặt trong chú thích để minh họa. \`IOException\` là checked exception; chữ ký \`run()\` không cho phép khai báo \`throws IOException\`. Không nên chỉ thay mọi checked exception thành RuntimeException mà không cân nhắc hợp đồng xử lý lỗi của ứng dụng.

### Khi nào Runnable phù hợp?

- Chạy tác vụ không yêu cầu trả về một giá trị, như gửi thông báo hoặc thực hiện một thao tác cập nhật đã được kiểm soát.
- Truyền công việc cho \`Executor.execute(Runnable)\` hoặc tạo \`Thread\` khi thực sự cần quản lý một luồng.
- Đăng ký callback mà API chỉ quan tâm hành động hoàn thành.

Khi cần một kết quả hoặc muốn dùng hợp đồng cho phép checked exception, \`Callable<V>\` thường phù hợp hơn.

## 4. Callable<V> là kiểu đích cho lambda không tham số, có kết quả

\`Callable<V>\` nằm trong gói \`java.util.concurrent\`; phương thức chức năng là \`V call() throws Exception\`. Lambda vẫn bắt đầu bằng \`() ->\`, nhưng cần tạo giá trị trả về tương thích với \`V\`.

~~~java
java.util.concurrent.Callable<Integer> count = () -> 40 + 2;

java.util.concurrent.Callable<String> buildMessage = () -> {
    String name = "Java";
    return "Xin chào " + name;
};
~~~

Đây là các đoạn minh họa; bên ngoài chúng cần ngữ cảnh khai báo Java phù hợp. Lambda biểu thức trả giá trị ngầm định; lambda khối dùng \`return\` trên những đường đi kết thúc bình thường.

\`call()\` có thể được gọi trực tiếp, nhưng việc gọi trực tiếp **không tự chạy ở luồng khác**:

~~~java
java.util.concurrent.Callable<String> work = () -> "Xong";
String result = work.call(); // Chạy đồng bộ trên luồng gọi.
~~~

Vì \`call()\` khai báo \`throws Exception\`, lời gọi trực tiếp phải được xử lý ngoại lệ hoặc được gọi trong phương thức có khai báo throws thích hợp.

Một \`Callable\` có thể ném checked exception bên trong:

~~~java
java.util.concurrent.Callable<String> read = () -> {
    throw new java.io.IOException("Không thể đọc");
};
~~~

Đoạn này chỉ minh họa khả năng khai báo ngoại lệ; không được gọi trong một chương trình chưa có xử lý lỗi. Kiểu kết quả \`String\` vẫn phù hợp: lambda luôn ném ngoại lệ nên không có đường đi bình thường cần trả giá trị.

### Khi nào Callable phù hợp?

- Một tác vụ nền cần trả về giá trị: truy vấn, tính toán, đọc dữ liệu hoặc dựng báo cáo.
- Một tác vụ có thể ném checked exception và bạn muốn báo lỗi cho nơi chờ kết quả.
- Giao việc qua \`ExecutorService.submit(Callable<V>)\`, nhận \`Future<V>\` để lấy giá trị khi hoàn thành.

**Callable không đồng nghĩa “bất đồng bộ”.** Tính bất đồng bộ phụ thuộc cách gọi hoặc nơi lên lịch tác vụ. Chỉ khai báo biến kiểu \`Callable\` chưa tạo ra bất kỳ luồng hay công việc chạy nền nào.

### Callable<Void> khác Runnable như thế nào?

Khi muốn dùng hợp đồng \`Callable\` nhưng không có giá trị có ý nghĩa, có thể dùng \`Callable<Void>\` và trả về \`null\`:

~~~java
java.util.concurrent.Callable<Void> save = () -> {
    System.out.println("Đã lưu");
    return null;
};
~~~

\`Void\` không phải \`void\`: \`Callable<Void>.call()\` vẫn là phương thức **trả về tham chiếu**, nên lambda khối phải trả về \`null\` trên đường đi bình thường. Nếu chỉ cần một hành động không kết quả và không cần hợp đồng checked exception, \`Runnable\` thường đơn giản hơn.

## 5. ExecutorService: cùng mô tả tác vụ, khác kết quả Future

Java 8 cung cấp \`ExecutorService\` để giao tác vụ cho worker. Khi gọi \`submit(Runnable)\`, bạn nhận \`Future<?>\` có thể chờ hoàn thành; sau khi hoàn thành bình thường, \`get()\` trả \`null\` nếu dùng overload một tham số \`submit(Runnable)\`. Khi gọi \`submit(Callable<V>)\`, bạn nhận \`Future<V>\` với giá trị do \`call()\` trả về.

Ví dụ hoàn chỉnh **RunnableCallableDemo.java**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RunnableCallableDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Runnable log = () ->
                System.out.println("Runnable: đã chạy");

            Callable<Integer> calculate = () -> {
                int x = 6;
                int y = 7;
                return x * y;
            };

            Future<?> logDone = executor.submit(log);
            Future<Integer> answer = executor.submit(calculate);

            System.out.println("Runnable.get(): " + logDone.get());
            System.out.println("Callable.get(): " + answer.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 RunnableCallableDemo.java
java RunnableCallableDemo
~~~

Kết quả:

~~~text
Runnable: đã chạy
Runnable.get(): null
Callable.get(): 42
~~~

**Giải thích:**

1. \`newSingleThreadExecutor()\` xử lý các tác vụ đã được chấp nhận lần lượt trên một worker, nên ví dụ có thứ tự in xác định.
2. \`executor.submit(log)\` trả về \`Future<?>.\` Tác vụ in câu thông báo nhưng không trả giá trị.
3. \`executor.submit(calculate)\` trả về \`Future<Integer>\`; \`call()\` trả 42.
4. \`Future.get()\` có thể **chặn luồng gọi** cho đến khi tác vụ hoàn thành. Nếu tác vụ ném lỗi, \`get()\` có thể ném \`ExecutionException\`; nếu bị ngắt khi chờ, có thể ném \`InterruptedException\`.
5. \`shutdown()\` yêu cầu executor ngừng nhận tác vụ mới và cho phép tác vụ đã nhận kết thúc; nó **không đồng nghĩa chờ đến khi mọi tác vụ hoàn thành**. Ở chương trình này cả hai \`get()\` đã chờ xong trước \`shutdown()\`.

Với ứng dụng thật, cần cân nhắc timeout, hủy tác vụ, kích thước pool và xử lý ngắt đúng cách. Ví dụ cố ý đơn giản để làm rõ **kiểu đích** và **kiểu kết quả**, không phải hướng dẫn thiết kế toàn bộ hệ thống xử lý nền.

### Khác nhau giữa execute và submit

| API | Chấp nhận | Trả ngay cho nơi gọi | Điểm quan sát lỗi/kết quả |
| --- | --- | --- | --- |
| \`Executor.execute(Runnable)\` | Runnable | \`void\` | Không có Future do phương thức này trả về; cách báo lỗi phụ thuộc executor/worker |
| \`ExecutorService.submit(Runnable)\` | Runnable | \`Future<?>\` | \`get()\` để chờ và nhận lỗi; kết quả bình thường là \`null\` |
| \`ExecutorService.submit(Callable<V>)\` | Callable<V> | \`Future<V>\` | \`get()\` để chờ, nhận giá trị V hoặc lỗi |

Ngoài ra còn overload \`submit(Runnable, T result)\`: nó trả \`Future<T>\` với kết quả được cung cấp riêng nếu tác vụ hoàn thành bình thường. Điều đó **không biến \`Runnable.run()\` thành phương thức trả T**. Kiểu đích của lambda vẫn là Runnable.

## 6. Checked exception đi từ Callable đến Future như thế nào?

Ví dụ hoàn chỉnh **CallableFailureDemo.java**:

~~~java
import java.io.IOException;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CallableFailureDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Callable<String> failing = () -> {
                throw new IOException("Thiếu dữ liệu");
            };
            Future<String> future = executor.submit(failing);

            try {
                System.out.println(future.get());
            } catch (ExecutionException ex) {
                System.out.println("Lỗi gốc: " +
                    ex.getCause().getClass().getSimpleName());
                System.out.println("Thông báo: " +
                    ex.getCause().getMessage());
            }
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CallableFailureDemo.java
java CallableFailureDemo
~~~

Kết quả:

~~~text
Lỗi gốc: IOException
Thông báo: Thiếu dữ liệu
~~~

\`Callable.call()\` cho phép ném \`IOException\`. Khi giao qua \`submit\`, ngoại lệ được giữ trong kết quả tác vụ; \`Future.get()\` báo bằng \`ExecutionException\`, và \`getCause()\` là ngoại lệ gốc. Đừng nhầm \`ExecutionException\` là loại lỗi mà lambda trực tiếp ném. Một chương trình sản xuất cũng nên xử lý/hủy đúng khi bị ngắt, và có thể dùng \`get(timeout, unit)\` nếu không được phép chờ vô hạn.

**Với Runnable được gửi bằng submit:** lỗi không được chứng minh là “biến mất”. Nó có thể được ghi nhận trong Future và xuất hiện khi gọi \`get()\`. Nhưng \`Runnable\` không có hợp đồng trả giá trị hay ném checked exception trực tiếp.

## 7. Comparator<T>: kiểu đích cho lambda hai tham số, trả int

\`Comparator<T>\` cung cấp quy tắc thứ tự giữa hai giá trị kiểu \`T\`. SAM là:

~~~java
int compare(T left, T right);
~~~

Đây là chữ ký minh họa, không phải định nghĩa lớp Java độc lập. Khi \`T\` là \`String\`, lambda có hai tham số \`String\` và phải trả một số \`int\`:

~~~java
java.util.Comparator<String> byLength =
    (left, right) -> Integer.compare(left.length(), right.length());
~~~

- Giá trị **âm**: \`left\` đứng trước \`right\`.
- Giá trị **0**: hai giá trị được coi là tương đương **theo quy tắc so sánh này**, không nhất thiết \`equals()\`.
- Giá trị **dương**: \`left\` đứng sau \`right\`.

Không có yêu cầu phải trả đúng \`-1\`, \`0\`, \`1\`; chỉ **dấu** là thông tin thứ tự. Nếu dùng Comparator cho sắp xếp, thuật toán dựa vào dấu đó để sắp xếp các phần tử.

### Tránh phép trừ khi so sánh số nguyên

Cách viết \`(a, b) -> a - b\` có thể gây **tràn số nguyên** khi a, b khác nhau nhiều, làm sai dấu kết quả. Dùng \`Integer.compare(a, b)\`, \`Long.compare(a, b)\` hoặc phương thức comparator phù hợp.

Ví dụ:

~~~java
java.util.Comparator<Integer> safe =
    (a, b) -> Integer.compare(a, b);
~~~

Khi đang so sánh một khóa kiểu nguyên thủy trong đối tượng, \`Comparator.comparingInt(...)\` vừa rõ mục đích vừa tránh boxing không cần thiết ở bước trích khóa.

### Comparator là quy tắc thứ tự, không phải kiểm tra lớn hơn

Không nên viết \`(a, b) -> a > b\` để gán vào \`Comparator<Integer>\` vì biểu thức trả về **boolean**, trong khi \`compare\` bắt buộc trả **int**. Cũng không thể dùng \`Comparator<String>\` với lambda không tham số, vì \`compare\` cần đúng hai đối số.

## 8. Sắp xếp bằng lambda và API Comparator hiện đại

Ví dụ hoàn chỉnh **ComparatorTargetDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class ComparatorTargetDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>(
            Arrays.asList("pear", "fig", "apple", "kiwi"));

        Comparator<String> byLength =
            (left, right) ->
                Integer.compare(left.length(), right.length());

        words.sort(byLength);
        System.out.println("Theo độ dài: " + words);

        Comparator<String> byLengthThenAlphabet =
            Comparator.comparingInt(String::length)
                      .thenComparing(Comparator.naturalOrder());

        words.sort(byLengthThenAlphabet);
        System.out.println("Độ dài + chữ cái: " + words);

        words.sort(byLengthThenAlphabet.reversed());
        System.out.println("Đảo thứ tự: " + words);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ComparatorTargetDemo.java
java ComparatorTargetDemo
~~~

Kết quả chính xác:

~~~text
Theo độ dài: [fig, pear, kiwi, apple]
Độ dài + chữ cái: [fig, kiwi, pear, apple]
Đảo thứ tự: [apple, pear, kiwi, fig]
~~~

**Giải thích:**

- \`words.sort(byLength)\` sửa danh sách tại chỗ theo độ dài tăng dần. \`List.sort\` bảo đảm **ổn định (stable)**: nếu hai phần tử được comparator coi tương đương, thứ tự tương đối ban đầu của chúng được giữ. Vì vậy pear đứng trước kiwi khi cùng độ dài 4.
- \`Comparator.comparingInt(String::length)\` xây comparator từ khóa độ dài kiểu \`int\`.
- \`thenComparing(Comparator.naturalOrder())\` dùng thứ tự chữ cái tự nhiên của String khi độ dài bằng nhau. Kiwi đứng trước pear.
- \`reversed()\` đảo **toàn bộ** quy tắc ghép, vì vậy độ dài trở thành giảm dần và tiêu chí chữ cái cũng bị đảo khi bằng độ dài. Nếu chỉ muốn giảm theo độ dài nhưng tăng theo chữ cái, cần ghép tiêu chí theo chiều mong muốn một cách tường minh.

Đây là tính năng Java 8 vẫn hợp lệ trên JDK hiện đại. Với danh sách không cho sửa, việc gọi \`sort\` có thể ném \`UnsupportedOperationException\`; nên dùng danh sách sửa được hoặc tạo bản sao trước khi sắp xếp.

### So sánh nhiều trường trong mã ứng dụng

Một trường hợp thực tế là sắp xếp người dùng theo tuổi rồi tên. Nếu có lớp \`Person\` với phương thức \`getAge()\` và \`getName()\`, ta có thể xây quy tắc:

~~~java
// Đoạn minh họa, cần lớp Person thích hợp:
Comparator<Person> byAgeThenName =
    Comparator.comparingInt(Person::getAge)
              .thenComparing(Person::getName);
~~~

Điểm chính: cách chọn thứ tự đến từ **Comparator<Person>** là kiểu đích; các method reference trong \`comparingInt\` và \`thenComparing\` cũng được suy luận kiểu từ chữ ký của API. Với một ứng dụng thật, cần quy định cách xử lý khóa null, quy tắc chuẩn hóa chữ hoa/chữ thường và tính ổn định của tiêu chí.

## 9. Hợp đồng Comparator: đúng thứ tự mới quan trọng

Một comparator phải cung cấp quan hệ so sánh nhất quán. Các nguyên tắc căn bản trong hợp đồng \`Comparator.compare\` là:

1. **Đối xứng dấu:** \`sign(compare(a,b))\` bằng dấu đối của \`compare(b,a)\`.
2. **Bắc cầu:** nếu a đứng sau b và b đứng sau c, a phải đứng sau c (tương tự cho chiều ngược).
3. **Nhất quán về nhóm tương đương:** nếu \`compare(a,b)==0\`, a và b phải có quan hệ so sánh cùng dấu với mọi phần tử khác theo hợp đồng.
4. Comparator có thể xem hai đối tượng tương đương dù \`equals()\` trả false. Tuy nhiên, khi dùng với \`TreeSet\` hoặc \`TreeMap\`, điều này ảnh hưởng đến cách cấu trúc dữ liệu coi các khóa là trùng nhau. Nếu cần hành vi tương thích với \`Set\`/Map theo \`equals\`, hãy thiết kế comparator nhất quán với equals.

Ví dụ chỉ so sánh độ dài:

~~~java
Comparator<String> byLength =
    (a, b) -> Integer.compare(a.length(), b.length());
~~~

\`byLength.compare("cat","dog") == 0\` nhưng \`"cat".equals("dog")\` là false. Nếu đưa cả hai vào một TreeSet dùng \`byLength\`, tập hợp coi chúng trùng nhau về thứ tự và chỉ giữ một phần tử đại diện. Đây là hệ quả của quy tắc so sánh, **không phải lỗi của lambda**.

**Không sửa trạng thái khiến tiêu chí so sánh thay đổi khi phần tử đang nằm trong cấu trúc dữ liệu dựa trên thứ tự**, đặc biệt trong \`TreeSet\` hoặc \`TreeMap\`. Việc thay đổi khóa có thể làm cấu trúc không còn hoạt động theo thứ tự mong đợi.

### Null và Comparator

Một comparator gọi \`left.length()\` không xử lý \`null\`. Nếu dữ liệu có thể null và yêu cầu đặt null trước, Java 8 có:

~~~java
Comparator<String> nullFirstByLength =
    Comparator.nullsFirst(Comparator.comparingInt(String::length));
~~~

Đoạn này minh họa; cần import Comparator và đặt trong vị trí khai báo hợp lệ. \`Comparator.nullsLast(...)\` đặt null sau. Lưu ý \`List.of\` trên JDK 9+ không cho phép phần tử null, trong khi nhiều nguồn danh sách khác có thể cho phép; hãy xác định điều kiện dữ liệu thực tế trước khi chọn quy tắc.

## 10. Cùng một lambda, ngữ cảnh kiểu khác nhau

### 10.1 Không dùng lambda tự do khi thiếu kiểu đích

Không hợp lệ:

~~~java
// Object job = () -> System.out.println("Chạy");
~~~

Dòng được chú thích vì \`Object\` không phải functional interface. Lambda chỉ được chấp nhận trong ngữ cảnh phù hợp với một giao diện hàm.

Viết đúng:

~~~java
Runnable job = () -> System.out.println("Chạy");
Object stored = job;
~~~

Giá trị \`stored\` ở đây là đối tượng đã được tạo ra theo kiểu đích Runnable; \`Object\` không thể trực tiếp làm kiểu đích khi tạo lambda.

### 10.2 Số tham số của SAM quyết định cú pháp

| Biểu thức | Runnable | Callable<String> | Comparator<String> |
| --- | --- | --- | --- |
| \`() -> System.out.println("OK")\` | Hợp lệ | Không hợp lệ (không trả String) | Không hợp lệ (thiếu hai tham số) |
| \`() -> "OK"\` | Không hợp lệ | Hợp lệ | Không hợp lệ |
| \`(a,b) -> a.compareTo(b)\` | Không hợp lệ | Không hợp lệ | Hợp lệ |
| \`() -> { return "OK"; }\` | Không hợp lệ | Hợp lệ | Không hợp lệ |
| \`() -> { System.out.println("OK"); }\` | Hợp lệ | Không hợp lệ (không trả String) | Không hợp lệ |

Lưu ý: \`Runnable\` có thể chấp nhận một **phương thức gọi dạng biểu thức** có trả giá trị nhưng được dùng như một câu lệnh trong một số ngữ cảnh void-compatible; điều đó không làm \`run()\` có kiểu trả về khác \`void\`. Chẳng hạn \`() -> someList.size()\` có thể tương thích với Runnable vì lời gọi phương thức là *statement expression*; giá trị trả về bị bỏ qua. Ngược lại, **chuỗi literal** \`() -> "OK"\` không phải statement expression hợp lệ cho thân void.

Đây là điểm quan trọng khi đọc lời gọi phương thức có overload nhận nhiều giao diện hàm: đôi khi cần chỉ rõ kiểu đích để người đọc và trình biên dịch hiểu ý định.

### 10.3 Làm rõ overload bằng biến trung gian

Giả sử có hai overload:

~~~java
void submitWork(Runnable task) { /* ... */ }
void submitWork(java.util.concurrent.Callable<String> task) { /* ... */ }
~~~

Đây chỉ là khai báo minh họa cho một lớp; **không phải chương trình chạy độc lập**. Thay vì dựa vào những quy tắc suy luận phức tạp khi truyền lambda trực tiếp, có thể viết:

~~~java
Runnable log = () -> System.out.println("Đã ghi");
java.util.concurrent.Callable<String> load = () -> "Dữ liệu";

submitWork(log);  // Chọn overload Runnable.
submitWork(load); // Chọn overload Callable<String>.
~~~

Biến trung gian giúp hợp đồng được bộc lộ rõ ràng. Một số lambda vốn tương thích nhiều đích có thể khiến lời gọi overload mơ hồ hoặc có kết quả chọn overload không như người mới học mong đợi. Hãy kiểm tra thông báo biên dịch cụ thể rồi khai báo kiểu chính xác; không cần đoán chỉ từ số tham số.

### 10.4 Khai báo rõ kiểu tham số nếu cần

Với Comparator<String>, Java thường suy luận được kiểu của hai tham số:

~~~java
Comparator<String> leftFirst =
    (a, b) -> a.compareTo(b);
~~~

Có thể ghi tường minh:

~~~java
Comparator<String> explicit =
    (String a, String b) -> a.compareTo(b);
~~~

Không được trộn \`(String a, b) -> ...\` vì hai tham số không cùng kiểu khai báo tường minh hoặc suy luận. Đặt biến rõ tên như \`left\`, \`right\` thường dễ đọc hơn \`a\`, \`b\` trong comparator phức tạp.

## 11. Method reference cũng cần kiểu đích

Cú pháp \`::\` là **method reference**, có thể thay lambda khi đã có phương thức phù hợp chữ ký SAM. Tương tự lambda, method reference cần ngữ cảnh kiểu đích:

~~~java
Runnable printLine = System.out::println;
java.util.concurrent.Callable<Double> randomValue = Math::random;
Comparator<String> natural = String::compareTo;
~~~

Ba dòng này là ví dụ khai báo trong ngữ cảnh thích hợp (với Comparator cần import). Tương ứng:

- \`System.out::println\` chọn overload không tham số khi kiểu đích là \`Runnable\`: gọi \`println()\`, trả \`void\`.
- \`Math::random\` phù hợp \`Callable<Double>\`: không tham số, trả \`double\` được boxing thành \`Double\`.
- \`String::compareTo\` có thể dùng theo dạng method reference của phương thức thể hiện (unbound instance method reference) cho hai chuỗi: tham số thứ nhất là đối tượng nhận lời gọi, tham số thứ hai là đối số; kết quả là int.

Ví dụ \`Comparator.comparingInt(String::length)\` minh họa một method reference một tham số; kiểu đích bên trong API \`comparingInt\` là giao diện hàm trích khóa kiểu int. Không nên kết luận từ riêng dấu \`::\` rằng có bao nhiêu tham số; phải nhìn chữ ký giao diện đích và cách liên kết receiver.

Method reference không luôn thay được lambda, chẳng hạn khi bạn cần thêm điều kiện, kết hợp nhiều thao tác hoặc xử lý ngoại lệ bên trong một khối. Chọn cách viết rõ nghĩa hơn với người đọc.

## 12. Chọn đúng kiểu đích trong bài toán thực tế

**Trường hợp 1 — Thực hiện một hành động không cần giá trị trả về:** chọn \`Runnable\` nếu API nhận Runnable. Mã sẽ được thực thi khi API gọi \`run()\`. Nếu chỉ dùng \`run()\` trực tiếp, đó là lời gọi đồng bộ trên luồng hiện tại.

**Trường hợp 2 — Lấy kết quả tính toán từ một tác vụ có thể chạy trên executor:** chọn \`Callable<V>\`; dùng \`Future<V>\` để đợi hoặc lấy kết quả. Quyết định executor, cơ chế timeout và xử lý lỗi là trách nhiệm của thiết kế thực thi, không do cú pháp lambda tự quyết định.

**Trường hợp 3 — Định nghĩa thứ tự sắp xếp:** chọn \`Comparator<T>\`; trả về số nguyên biểu diễn dấu của quan hệ thứ tự. Ưu tiên các công cụ \`comparing\`, \`comparingInt\`, \`thenComparing\`, \`reversed\`, \`nullsFirst\` và \`nullsLast\` khi chúng biểu diễn rõ yêu cầu.

**Trường hợp 4 — Một API yêu cầu một chức năng khác:** đừng ép dùng ba giao diện trên nếu hợp đồng thực sự là \`Supplier<T>\`, \`Consumer<T>\`, \`Function<T,R>\`, \`Predicate<T>\`, \`BiFunction<T,U,R>\`, v.v. Số tham số/kiểu trả về của SAM luôn là tiêu chí chọn đúng.

Khi một phương thức nhận \`Runnable\`, việc viết lambda \`() -> ...\` không khiến nó tự chuyển thành Callable. Khi một phương thức nhận Comparator, không thể trả \`boolean\` chỉ vì logic “a nhỏ hơn b” trông đơn giản hơn.

## 13. Những lỗi phổ biến và cách sửa

| Lỗi | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Gán \`() -> 42\` cho Runnable | Literal trả giá trị, không hợp đồng \`void run()\` | Dùng \`Callable<Integer>\` hoặc \`Supplier<Integer>\` |
| Gán \`() -> { System.out.println("Hi"); }\` cho Callable<String> | Thiếu kết quả String trên đường chạy bình thường | Thêm \`return "..." \` hoặc chọn Runnable |
| Gán \`(a,b) -> a > b\` cho Comparator<Integer> | compare phải trả \`int\`, không phải boolean | \`(a,b) -> Integer.compare(a,b)\` |
| Gán \`() -> ...\` cho Comparator | SAM cần hai tham số | Viết \`(left,right) -> ...\` |
| Viết \`(a,b) -> a-b\` để so sánh int | Có thể tràn số làm sai thứ tự | Dùng \`Integer.compare(a,b)\` |
| Tưởng \`Runnable.run()\` khởi tạo thread | Gọi trực tiếp chạy trên thread hiện tại | Giao Runnable cho Executor/Thread khi thực sự cần |
| Tưởng \`Callable.call()\` tự chạy bất đồng bộ | Callable chỉ mô tả tác vụ | Dùng \`ExecutorService.submit\` nếu muốn lên lịch |
| Bỏ qua \`Future.get()\` khi cần kết quả hoặc lỗi | Chưa quan sát trạng thái hoàn thành | Lấy Future và xử lý kết quả/ngoại lệ đúng điểm |
| Ném IOException trực tiếp từ Runnable | \`run()\` không cho checked exception | Xử lý trong thân hoặc chọn Callable đúng hợp đồng |
| Dùng comparator thay đổi theo thời gian | Vi phạm tính nhất quán của thứ tự | Dùng khóa ổn định và comparator có quy tắc rõ ràng |
| Dùng comparator chỉ xét một trường trong TreeSet mà mong giữ tất cả giá trị \`equals\` khác nhau | \`compare == 0\` được TreeSet coi là trùng | Bổ sung tiêu chí phân biệt phù hợp |
| Dựa vào lambda mà bỏ qua kiểu đích | Thiếu thông tin về tham số/kết quả | Đọc chữ ký SAM hoặc khai báo biến giao diện rõ ràng |

## 14. Thực hành có đáp án

**Bài 1 — Dự đoán kiểu đích và kết quả.**

~~~java
Runnable r = () -> System.out.println("A");
java.util.concurrent.Callable<String> c = () -> "B";
java.util.Comparator<String> order = (x, y) -> x.compareTo(y);
~~~

Đây là đoạn minh họa trong phương thức. Hỏi: ba lambda lần lượt có bao nhiêu tham số, trả về loại gì? **Đáp án:** Runnable: 0 và void; Callable<String>: 0 và String; Comparator<String>: 2 tham số String và int. Việc tạo các biến không tự in A hay trả B; cần gọi SAM hoặc giao cho API phù hợp.

**Bài 2 — Sửa lỗi Comparator.** Thay \`(a,b) -> a-b\` bằng phép so sánh an toàn cho hai \`Integer\`. **Đáp án:** \`(a,b) -> Integer.compare(a,b)\`. Khi muốn sắp xếp chuỗi theo độ dài, dùng \`Comparator.comparingInt(String::length)\`, có thể ghép \`thenComparing(Comparator.naturalOrder())\` để phân biệt các chuỗi cùng độ dài.

**Bài 3 — Chọn giao diện.** Một tác vụ trả số lượng bản ghi và có thể ném IOException, sau đó được gửi qua \`ExecutorService.submit\`. Nên dùng \`Runnable\` hay \`Callable<Integer>\`? **Đáp án:** Callable<Integer> vì cần giá trị và hợp đồng ném checked exception; \`Future<Integer>.get()\` nhận giá trị hoặc \`ExecutionException\` nếu tác vụ thất bại.

**Bài 4 — Phân biệt thời điểm thực thi.** Với \`Runnable r = () -> log();\`, câu lệnh nào khởi động luồng mới: \`r.run()\`, \`new Thread(r).start()\`, hay chỉ khai báo r? **Đáp án:** \`new Thread(r).start()\` yêu cầu tạo và bắt đầu một luồng mới; \`r.run()\` chỉ gọi phương thức trên luồng hiện tại; chỉ khai báo r chưa chạy phần thân. Trong ứng dụng thực tế, thường ưu tiên executor có quản lý tài nguyên phù hợp thay vì tạo vô hạn luồng thủ công.

**Bài 5 — Kiểm tra số tham số.** \`Comparator<String> c = (x) -> x.length();\` có hợp lệ không? **Đáp án:** không, vì compare(String,String) nhận **hai** đối số. Lambda một tham số kiểu String trả về int có thể phù hợp \`ToIntFunction<String>\` hoặc \`Function<String,Integer>\`, nhưng không phù hợp Comparator<String>.

## Ghi nhớ

- \`Runnable\` → \`() -> ...\`, SAM \`void run()\`: **không tham số, không giá trị trả về**.
- \`Callable<V>\` → \`() -> ...\`, SAM \`V call() throws Exception\`: **không tham số, có kết quả kiểu V, có thể ném checked exception**.
- \`Comparator<T>\` → \`(left, right) -> ...\`, SAM \`int compare(T,T)\`: **hai tham số và kết quả int diễn tả thứ tự**.
- Lambda/method reference cần **kiểu đích** để suy luận kiểu và kiểm tra sự tương thích; số tham số tương tự chưa đủ để coi hai giao diện có cùng hợp đồng.
- \`run()\` hoặc \`call()\` gọi trực tiếp đều chạy trên luồng gọi. Chỉ cơ chế lên lịch như \`ExecutorService\` mới quyết định cách tác vụ được thực thi.
- Comparator đúng phải có quy tắc thứ tự nhất quán. Sử dụng \`Integer.compare\` và các phương thức ghép comparator rõ ràng; kiểm tra hệ quả của \`compare == 0\` với cấu trúc cây.

Khi gặp một lambda trong mã thực tế, hãy bắt đầu bằng câu hỏi **“Phương thức nào của giao diện đích sẽ được triển khai?”**. Từ đó việc hiểu tham số, kết quả, ngoại lệ và cách dùng sẽ có cơ sở rõ ràng.