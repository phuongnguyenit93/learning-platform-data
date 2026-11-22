# Phân biệt tham chiếu được giữ cố định với đối tượng bất biến trong Java

## Mục tiêu học tập

Trong Java, một biến có thể **không được phép gán lại** nhưng đối tượng mà biến đang trỏ tới vẫn **có thể thay đổi trạng thái**. Sự khác biệt này đặc biệt quan trọng khi viết lambda: Java yêu cầu biến cục bộ được lambda sử dụng phải là **final** hoặc **effectively final**, nhưng quy tắc đó không tự biến dữ liệu bên trong đối tượng thành bất biến.

Sau bài này, bạn sẽ phân biệt chính xác việc giữ cố định một tham chiếu với tính bất biến của đối tượng; hiểu quy tắc bắt giữ biến (variable capture) trong lambda; kiểm tra các trường hợp có nhiều tham chiếu trỏ tới cùng một đối tượng; biết vì sao các lớp vỏ không cho sửa chưa chắc tạo ra bản sao độc lập; và áp dụng các nguyên tắc này để viết mã rõ ràng, dễ kiểm tra và an toàn khi cần dùng chung dữ liệu.

Những quy tắc nêu dưới đây vẫn áp dụng trong Java hiện đại. Các ví dụ chính dùng cú pháp Java 8 và chạy được trên JDK 8 trở lên.

## 1. Hai câu hỏi hoàn toàn khác nhau

**Tham chiếu được giữ cố định (fixed reference)** trả lời câu hỏi: **“Biến này có được phép trỏ sang đối tượng khác hay không?”**

**Đối tượng bất biến (immutable object)** trả lời câu hỏi: **“Sau khi tạo xong, trạng thái quan sát được của đối tượng này có thể bị thay đổi hay không?”**

Hãy xem:

~~~java
final StringBuilder text = new StringBuilder("Java");
text.append(" 8");                  // Hợp lệ: sửa trạng thái đối tượng.
System.out.println(text);         // Java 8

// text = new StringBuilder("JDK"); // Không hợp lệ: gán lại biến final.
~~~

Đây là **đoạn minh họa** cần đặt trong một phương thức/lớp phù hợp; không phải chương trình Java độc lập. Từ khóa **final** áp dụng cho **biến text**. Nó ngăn gán một tham chiếu mới vào biến đó, nhưng không cấm gọi **append** trên StringBuilder vốn có thể thay đổi.

Ngược lại:

~~~java
String message = "Java";
message = "Java 8"; // Hợp lệ: biến không final nên được gán lại.
~~~

**String** là một kiểu bất biến: phép gán thứ hai khiến **message** tham chiếu tới một chuỗi khác, không sửa nội dung của chuỗi ban đầu. Ngay cả **message.concat(" 8")** cũng tạo ra giá trị chuỗi mới thay vì sửa chuỗi cũ; muốn giữ kết quả cần sử dụng giá trị trả về.

Vậy có bốn khả năng:

| Biến tham chiếu | Đối tượng mà biến tham chiếu | Có thể gán lại biến? | Có thể sửa trạng thái đối tượng qua API thông thường? |
| --- | --- | --- | --- |
| final | Mutable, ví dụ StringBuilder | Không | Có |
| Không final | Mutable, ví dụ ArrayList | Có | Có |
| final | Immutable, ví dụ String | Không | Không |
| Không final | Immutable, ví dụ String | Có | Không |

Hai khía cạnh **độc lập**. Đừng đồng nhất “không đổi biến” với “không đổi dữ liệu”.

## 2. Khi nào một tham chiếu được giữ cố định?

Trong Java, biến kiểu tham chiếu chứa một **tham chiếu tới đối tượng** (hoặc null), không chứa bản sao toàn bộ đối tượng. Câu lệnh gán thông thường sao chép giá trị tham chiếu, nên hai biến có thể cùng trỏ tới một đối tượng.

- **Biến cục bộ final:** sau khi được gán, không thể gán lại; không bảo đảm đối tượng bất biến.
- **Biến cục bộ effectively final:** không viết từ khóa final nhưng sau khi khởi tạo/gán theo quy tắc của Java, giá trị biến không bị gán lại. Java dùng khái niệm này khi kiểm tra các biến cục bộ được lambda bắt giữ.
- **Trường (field) final:** trường chỉ được gán theo các quy tắc khởi tạo của Java; trường tham chiếu final vẫn có thể trỏ tới đối tượng mutable.
- **Tham chiếu đến đối tượng bất biến:** dù biến final hay không, đối tượng vẫn không cho phép thay đổi trạng thái qua API của chính nó.

Ví dụ:

~~~java
final java.util.List<String> list = new java.util.ArrayList<>();
list.add("A"); // Hợp lệ.
list.add("B"); // Hợp lệ.
// list = new java.util.ArrayList<>(); // Lỗi biên dịch.
~~~

Đoạn này minh họa **final List** chứ không có nghĩa “danh sách bất biến”. Khi thấy khai báo **final List<T>**, chỉ có thể kết luận rằng biến/trường final không thể được gán sang danh sách khác theo cách thông thường. Muốn biết danh sách có sửa được không, phải xem đối tượng thực tế và cách dữ liệu được bảo vệ.

**Lưu ý về kiểu nguyên thủy:** với **final int count = 5**, bản thân biến giữ giá trị 5 và không được gán lại. Không có “đối tượng int” nào được biến đó trỏ tới để phân biệt tính mutable; cách diễn giải fixed reference chỉ áp dụng trực tiếp với biến kiểu tham chiếu.

## 3. Vì sao lambda cho phép dùng biến effectively final?

Java 8 cho phép lambda đọc biến cục bộ trong phạm vi bên ngoài khi biến đó là **final** hoặc **effectively final**. Quy tắc áp dụng cho **biến cục bộ, tham số phương thức và tham số của khối catch** được bắt giữ, không có nghĩa mọi đối tượng liên quan cũng phải bất biến.

Ví dụ:

~~~java
String prefix = "ID-";               // effectively final
java.util.function.Function<Integer, String> label =
    number -> prefix + number;
System.out.println(label.apply(7));  // ID-7
~~~

Đây là đoạn minh họa cần đặt trong phương thức/lớp thích hợp. **prefix** không bị gán lại nên hợp lệ dù không khai báo từ khóa final. Nếu sau đó bổ sung **prefix = "CODE-";** trong cùng phạm vi, chương trình sẽ không biên dịch vì biến được lambda bắt giữ không còn effectively final.

**“Effectively final” là ràng buộc về phép gán của biến**, không phải bất biến đệ quy của giá trị mà biến tham chiếu. Một biến trỏ tới StringBuilder có thể vẫn effectively final trong khi nội dung StringBuilder đổi:

~~~java
StringBuilder builder = new StringBuilder("A");
Runnable appendB = () -> builder.append("B");
appendB.run();
System.out.println(builder); // AB
~~~

Lambda hợp lệ vì **builder** không bị gán lại. Phương thức **append** sửa đối tượng nên nội dung thay đổi. Đây là ví dụ đặc trưng của **tham chiếu được giữ cố định nhưng đối tượng có thể thay đổi**.

### Vì sao lại có quy tắc đó?

Biến cục bộ thuộc phạm vi lần gọi phương thức. Lambda có thể được lưu và gọi **sau khi phương thức tạo ra nó đã kết thúc**. Java bắt giữ giá trị của biến cục bộ phù hợp; không biến biến cục bộ thành một ô nhớ chia sẻ để có thể tùy ý gán lại giữa bên ngoài và lambda.

Không nên diễn giải rằng mọi lambda luôn giữ một bản sao độc lập của **đối tượng**. Với biến tham chiếu, giá trị được bắt giữ là **tham chiếu**. Do đó lambda và mã bên ngoài có thể nhìn vào **cùng một đối tượng mutable**, như StringBuilder ở trên.

### Quy tắc không đồng nghĩa mọi trạng thái đều final

Lambda cũng có thể đọc/ghi **trường đối tượng** trong ngữ cảnh thích hợp. Quy tắc effectively final của biến cục bộ không áp đặt lên mọi field. Tuy vậy, việc nhiều luồng cùng sửa field vẫn cần cơ chế đồng bộ theo mô hình bộ nhớ Java; tính hợp lệ khi biên dịch không bảo đảm an toàn khi chạy đồng thời.

## 4. Ví dụ chạy được: biến không gán lại, đối tượng vẫn đổi

Tạo tệp **LambdaFixedReferenceDemo.java**:

~~~java
import java.util.function.Supplier;

public class LambdaFixedReferenceDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("Java");

        Supplier<String> currentText = () -> builder.toString();
        Runnable addVersion = () -> builder.append(" 8");

        System.out.println("Trước: " + currentText.get());
        addVersion.run();
        System.out.println("Sau: " + currentText.get());

        final StringBuilder fixed = new StringBuilder("Hello");
        fixed.append(" World");
        System.out.println("final: " + fixed);

        final String immutable = "Hi";
        String next = immutable.concat(" Java");
        System.out.println("String cũ: " + immutable);
        System.out.println("String mới: " + next);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 LambdaFixedReferenceDemo.java
java LambdaFixedReferenceDemo
~~~

Kết quả chính xác:

~~~text
Trước: Java
Sau: Java 8
final: Hello World
String cũ: Hi
String mới: Hi Java
~~~

**Giải thích từng điểm:**

1. **builder** là biến cục bộ effectively final vì không bị gán lại. Cả hai lambda cùng sử dụng tham chiếu tới một StringBuilder.
2. **currentText** đọc trạng thái hiện thời lúc gọi **get()**; nó không chụp ảnh nội dung StringBuilder tại thời điểm tạo lambda.
3. **addVersion.run()** sửa đối tượng; vì thế lần **get()** sau trả về "Java 8".
4. **fixed** có từ khóa final nhưng vẫn cho phép **append**.
5. **immutable** trỏ tới đối tượng String bất biến; **concat** trả về chuỗi khác mà không sửa chuỗi ban đầu.

Trong chương trình này mọi lời gọi đều thực hiện lần lượt trên luồng chính. Bài chỉ chứng minh **khác biệt về trạng thái đối tượng**, không giả định có chạy song song.

## 5. Nhiều biến có thể cùng tham chiếu một đối tượng

Xét một danh sách:

~~~java
java.util.List<String> first = new java.util.ArrayList<>();
java.util.List<String> second = first;

second.add("A");
System.out.println(first); // [A]
~~~

Đây là đoạn minh họa, không phải tệp Java độc lập. Phép gán **second = first** không sao chép ArrayList: cả hai biến chỉ tới một danh sách.

Ngay cả khi **first** được khai báo final, biến **second** vẫn có thể thay đổi nội dung của danh sách. Giữ cố định tham chiếu không loại bỏ khả năng **aliasing** (nhiều tham chiếu cùng trỏ đến đối tượng).

Hệ quả thực tế:

- Một phương thức nhận đối số là List có thể sửa danh sách do người gọi sở hữu nếu API cho phép.
- Một getter trả trực tiếp danh sách nội bộ có thể làm lộ trạng thái mutable.
- Một lambda bắt giữ tham chiếu tới danh sách không nhận bản sao danh sách chỉ vì biến cục bộ là final.
- Nếu nhiều luồng cùng truy cập danh sách mutable, cần phân biệt trường hợp chỉ đọc sau khi công bố an toàn với trường hợp có thay đổi đồng thời.

**Java truyền tham số theo giá trị (pass by value):** với đối số kiểu tham chiếu, giá trị được sao chép để truyền đi là **tham chiếu**, không phải đối tượng. Một phương thức có thể sửa trạng thái đối tượng qua tham chiếu được nhận, nhưng gán lại biến tham số bên trong phương thức không làm biến của người gọi trỏ sang đối tượng khác.

## 6. Danh sách không cho sửa, bản sao và đối tượng thật sự bất biến

Một nguồn nhầm lẫn phổ biến là **Collections.unmodifiableList(...)**.

Trong Java 8, phương thức này tạo một **lớp vỏ không cho sửa qua tham chiếu được trả về**. Nó không tự sao chép dữ liệu. Nếu danh sách gốc được sửa qua tham chiếu khác, danh sách nhìn qua lớp vỏ có thể thay đổi theo.

Tạo tệp **UnmodifiableVersusSnapshotDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class UnmodifiableVersusSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(Arrays.asList("A"));

        List<String> readOnlyView =
            Collections.unmodifiableList(source);

        List<String> snapshot =
            Collections.unmodifiableList(new ArrayList<>(source));

        System.out.println("Ban đầu - view: " + readOnlyView);
        System.out.println("Ban đầu - copy: " + snapshot);

        source.add("B");

        System.out.println("Sau sửa nguồn - view: " + readOnlyView);
        System.out.println("Sau sửa nguồn - copy: " + snapshot);

        try {
            readOnlyView.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Không sửa được qua view");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 UnmodifiableVersusSnapshotDemo.java
java UnmodifiableVersusSnapshotDemo
~~~

Kết quả chính xác:

~~~text
Ban đầu - view: [A]
Ban đầu - copy: [A]
Sau sửa nguồn - view: [A, B]
Sau sửa nguồn - copy: [A]
Không sửa được qua view
~~~

**Phân tích:**

- **readOnlyView** không cho gọi add() thành công, nhưng phản ánh thay đổi đã thực hiện trực tiếp trên **source**. Đây là **view không cho sửa**, không phải bản chụp bất biến của dữ liệu nguồn.
- **snapshot** có một ArrayList riêng nên thao tác **source.add("B")** không làm thay đổi cấu trúc của bản sao. Lớp vỏ ngăn người nhận sửa danh sách qua chính tham chiếu snapshot.
- Tuy nhiên, phép sao chép ArrayList là **sao chép nông (shallow copy)**. Nếu phần tử là đối tượng mutable (chẳng hạn một lớp Person có setter), danh sách nguồn và danh sách sao chép vẫn có thể giữ tham chiếu tới cùng phần tử. Muốn bất biến sâu cần xem cả trạng thái của phần tử.
- Hai biến **readOnlyView** và **snapshot** nếu được khai báo final thì chỉ bổ sung việc không gán lại biến; cách hoạt động của danh sách không thay đổi.

Trên JDK 10+, **List.copyOf(source)** giúp tạo danh sách không cho sửa với các phần tử được giữ theo tham chiếu; nó không phải phép sao chép sâu. **List.of(...)** có từ JDK 9+ cũng tạo danh sách không cho sửa. Những API này hữu ích trong mã hiện đại nhưng **không có trong Java 8**. Với nội dung tập trung Java 8, cách sao chép phòng vệ rồi dùng Collections.unmodifiableList vẫn là ví dụ phù hợp.

Không nên gọi **Collections.unmodifiableList(source)** là một “bản sao bất biến”. Cũng không nên cho rằng đối tượng chứa **final List** thì mọi phần tử của danh sách tự nhiên trở nên bất biến.

## 7. Một kiểu dữ liệu bất biến cần những điều kiện gì?

Không có một từ khóa **immutable** chung nào tự động áp dụng cho mọi lớp Java. Tính bất biến là **thiết kế của kiểu dữ liệu**: trạng thái quan sát được cần giữ ổn định sau khi tạo đối tượng.

Các nguyên tắc thường hữu ích:

1. Không cung cấp thao tác sửa trạng thái quan sát được sau khi khởi tạo.
2. Với các trường lưu trạng thái nội bộ, dùng **private final** khi phù hợp để tránh bị gán lại và hạn chế lộ trạng thái.
3. Nếu nhận dữ liệu mutable từ bên ngoài, **sao chép phòng vệ** trước khi lưu trữ khi cần quyền sở hữu độc lập.
4. Nếu trả dữ liệu mutable ra bên ngoài, tránh trả trực tiếp tham chiếu cho phép sửa trạng thái nội bộ; trả bản sao hoặc một dạng bất biến phù hợp.
5. Nếu lớp có phần tử hoặc đối tượng lồng nhau mutable, phải quyết định có cần sao chép sâu hoặc sử dụng kiểu phần tử bất biến hay không.
6. Cân nhắc kế thừa: nếu một lớp cho phép lớp con thay đổi hành vi/trạng thái mà người dùng quan sát, thiết kế bất biến có thể không còn được bảo toàn.

**Chỉ dùng final trên các field là chưa đủ.** Chẳng hạn **private final List<String> items** ngăn gán lại field nhưng không ngăn **items.add("X")** khi đối tượng thực tế là ArrayList.

### Ví dụ lớp bất biến có sao chép phòng vệ

Tạo tệp **ImmutableConfigDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.function.Supplier;

public class ImmutableConfigDemo {

    public static final class Config {
        private final String name;
        private final List<String> features;

        public Config(String name, List<String> features) {
            if (name == null || features == null ||
                    features.contains(null)) {
                throw new IllegalArgumentException("Dữ liệu không hợp lệ");
            }
            this.name = name;
            this.features = Collections.unmodifiableList(
                new ArrayList<>(features));
        }

        public String getName() {
            return name;
        }

        public List<String> getFeatures() {
            return features;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(
            Arrays.asList("logging"));

        Config config = new Config("Service", input);
        Supplier<String> description =
            () -> config.getName() + " -> " + config.getFeatures();

        input.add("metrics");

        System.out.println("Nguồn: " + input);
        System.out.println("Cấu hình: " + description.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ImmutableConfigDemo.java
java ImmutableConfigDemo
~~~

Kết quả:

~~~text
Nguồn: [logging, metrics]
Cấu hình: Service -> [logging]
~~~

Trong thiết kế cụ thể này, **String** là bất biến, các phần tử của **features** là String bất biến, cấu trúc danh sách được sao chép và chỉ lộ ra qua lớp vỏ không cho sửa. **Config** là lớp final, không có setter và không lộ tham chiếu mutable bên trong. Vì thế, với hai trường đó, trạng thái quan sát được không bị thay đổi do người dùng sửa danh sách input sau khi tạo Config.

Lambda **description** bắt giữ biến **config** effectively final. Tính bất biến của **Config** đến từ thiết kế lớp và việc sao chép phòng vệ; nó **không được sinh ra** bởi quy tắc effectively final của lambda.

Trên JDK hiện đại, **record** giúp viết gọn các lớp mang dữ liệu bằng cách tạo thành phần final và các phương thức cơ bản, nhưng record **không mặc nhiên bất biến sâu**: một thành phần kiểu List vẫn có thể tham chiếu tới danh sách mutable nếu không có thiết kế sao chép phù hợp. Record là tính năng chuẩn từ Java 16, không phải cú pháp Java 8.

## 8. Tính bất biến và an toàn khi dùng lambda với nhiều luồng

Từ việc **biến captured là effectively final** không thể kết luận rằng lambda luôn an toàn để chạy song song.

Ví dụ, một lambda có thể bắt giữ **final ArrayList** và gọi **add** từ nhiều worker. Tham chiếu không đổi nhưng ArrayList vẫn mutable và không được thiết kế để chịu sửa đồng thời mà không phối hợp. Kết quả có thể không chính xác, xuất hiện lỗi hoặc gây vấn đề về tính nhất quán. Điều quan trọng là **trạng thái chia sẻ** và cách các luồng truy cập nó.

Với nhu cầu đếm an toàn, có thể dùng **AtomicInteger**; đối tượng này **có thể thay đổi**, nhưng cung cấp những thao tác nguyên tử được thiết kế cho truy cập đồng thời.

Tạo tệp **CapturedCounterDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class CapturedCounterDemo {
    public static void main(String[] args) throws Exception {
        final AtomicInteger counter = new AtomicInteger(0);
        ExecutorService workers = Executors.newFixedThreadPool(2);

        Runnable increment = () -> {
            for (int i = 0; i < 1_000; i++) {
                counter.incrementAndGet();
            }
        };

        try {
            Future<?> first = workers.submit(increment);
            Future<?> second = workers.submit(increment);

            first.get();
            second.get();

            System.out.println("Kết quả: " + counter.get());
        } finally {
            workers.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CapturedCounterDemo.java
java CapturedCounterDemo
~~~

Kết quả:

~~~text
Kết quả: 2000
~~~

**counter** là một tham chiếu final trỏ tới đối tượng mutable. Mỗi lần incrementAndGet() thay đổi giá trị nội bộ bằng thao tác nguyên tử; hai luồng có thể cùng thực hiện những lượt tăng mà không làm mất cập nhật. Sau khi cả hai Future.get() hoàn thành bình thường, chương trình có thể in tổng chính xác.

Không được suy ra rằng **final AtomicInteger** là một số bất biến. Tính đúng ở đây do **API nguyên tử** cùng cách chờ kết thúc tác vụ, không phải do từ khóa final.

Khi công việc không cần trạng thái chung, cách dễ kiểm chứng thường là cho mỗi tác vụ tính kết quả riêng, sau đó ghép kết quả tại một điểm xác định. Bất biến giúp giảm nhiều kiểu lỗi do dữ liệu chia sẻ; tuy vậy vẫn phải xét việc công bố đối tượng giữa các luồng, các thao tác I/O, tài nguyên khác và thiết kế của toàn bộ hệ thống.

**Không nên dùng một mảng một phần tử hoặc đối tượng mutable chỉ để “lách” yêu cầu effectively final** cho biến đếm cục bộ. Cách này che giấu trạng thái có thể thay đổi, và khi đưa vào nhiều luồng vẫn có nguy cơ race condition. Chỉ dùng trạng thái mutable được bắt giữ khi nó thực sự phù hợp với bài toán và có cách kiểm soát rõ ràng.

## 9. Những câu khẳng định thường gây hiểu nhầm

| Khẳng định | Đánh giá | Lý do |
| --- | --- | --- |
| “final StringBuilder là bất biến.” | Sai | final ngăn gán lại biến; StringBuilder vẫn có append/delete. |
| “Biến được lambda bắt giữ phải khai báo final.” | Sai | Effectively final là đủ; không bắt buộc viết từ khóa. |
| “Biến effectively final thì đối tượng nó trỏ tới không đổi.” | Sai | Có thể sửa trạng thái đối tượng qua phương thức như add/append. |
| “String không final thì String có thể bị chỉnh sửa.” | Sai | Biến có thể được gán lại; bản thân đối tượng String vẫn bất biến. |
| “Hai biến cùng trỏ ArrayList thì mỗi biến có một bản sao riêng.” | Sai | Gán biến kiểu tham chiếu sao chép tham chiếu, không sao chép đối tượng. |
| “Collections.unmodifiableList(source) chụp ảnh dữ liệu nguồn.” | Sai | Đây là view; sửa nguồn qua tham chiếu khác vẫn có thể hiện lên view. |
| “Bản sao danh sách luôn bất biến sâu.” | Sai | Sao chép thông thường chỉ sao chép tham chiếu tới phần tử. |
| “Tất cả field final nghĩa là cả object bất biến sâu.” | Sai | Đối tượng tham chiếu trong field vẫn có thể mutable. |
| “record luôn bất biến sâu.” | Sai | Thành phần tham chiếu có thể trỏ tới object mutable. |
| “final bảo đảm an toàn khi nhiều thread cùng sửa object.” | Sai | Cần xem dữ liệu dùng chung và cơ chế đồng bộ tương ứng. |

### Thêm một lưu ý về null

Một biến **final** kiểu tham chiếu có thể được gán **null** khi khởi tạo và sau đó không được gán lại. Điều này không nói gì về tính bất biến của một đối tượng, vì biến đó hiện không trỏ tới đối tượng nào.

### Thêm một lưu ý về việc trả tham chiếu

Ngay cả khi một getter **không có setter**, nếu getter trả về trực tiếp một ArrayList nội bộ, bên gọi vẫn có thể sửa danh sách. **Không có setter** chưa đủ để kết luận đối tượng bất biến. Cần kiểm tra toàn bộ các đường cho phép quan sát hoặc sửa trạng thái.

## 10. Bài tập và câu hỏi tự kiểm tra

**Bài 1 — Phân loại.** Xem các khai báo sau và phân biệt *biến tham chiếu có được gán lại không* với *đối tượng có thể sửa không*:

~~~java
final StringBuilder a = new StringBuilder("A");
String b = "B";
final java.util.List<Integer> c = new java.util.ArrayList<>();
~~~

Đáp án: **a** không được gán sang StringBuilder khác nhưng có thể append; **b** được gán sang String khác nhưng đối tượng String không sửa được; **c** không được gán sang List khác nhưng danh sách ArrayList có thể add/remove. Đây là các khai báo minh họa, cần đặt trong ngữ cảnh Java hợp lệ.

**Bài 2 — Lambda và phép gán.** Cho:

~~~java
StringBuilder text = new StringBuilder("X");
Runnable task = () -> text.append("Y");
task.run();
~~~

Kết quả **text.toString()** là gì? Có lỗi effectively final không? Trả lời: **"XY"**, không có lỗi vì biến **text** không bị gán lại. Nếu thêm phép gán **text = new StringBuilder("Z")** trong cùng phương thức, tham chiếu tới text trong lambda sẽ không còn hợp lệ khi biên dịch.

**Bài 3 — View hay bản sao?** Với **source** là ArrayList<String>, so sánh:

~~~java
java.util.List<String> view =
    java.util.Collections.unmodifiableList(source);

java.util.List<String> copy =
    java.util.Collections.unmodifiableList(
        new java.util.ArrayList<>(source));
~~~

Nếu gọi **source.add("new")**, **view** có thể phản ánh phần tử mới; **copy** không thay đổi cấu trúc vì được tạo từ danh sách sao chép trước đó. Nếu phần tử là kiểu mutable, cả hai vẫn có thể cùng giữ tham chiếu tới một phần tử cụ thể.

**Bài 4 — Thiết kế lớp.** Một lớp lưu **private final List<MutableItem> items** rồi trả **items** trực tiếp trong getter. Hãy chỉ ra hai đường thay đổi có thể xảy ra: người dùng có thể sửa cấu trúc danh sách (nếu danh sách cho phép), và có thể sửa trạng thái của từng MutableItem qua tham chiếu phần tử. Đề xuất cách kiểm soát phù hợp với yêu cầu bất biến, bao gồm sao chép hoặc chuyển đổi phần tử.

**Bài 5 — Dùng nhiều luồng.** Hai worker cùng chạy **counter.incrementAndGet()** trên một AtomicInteger được lambda bắt giữ. Điều gì bảo đảm phép tăng không mất cập nhật? Đáp án: **incrementAndGet() có tính nguyên tử**; final/effectively final chỉ giúp tham chiếu captured không bị gán lại trong phạm vi biến cục bộ.

## Tổng kết

**Tham chiếu cố định** là thuộc tính của **biến**: final hoặc effectively final giới hạn việc gán lại. **Đối tượng bất biến** là thuộc tính của **thiết kế đối tượng**: trạng thái quan sát được không đổi sau khi tạo.

Với lambda, một biến cục bộ được bắt giữ phải là final hoặc effectively final, nhưng đối tượng mà biến ấy trỏ tới vẫn có thể mutable. Khi cần dữ liệu ổn định, hãy xem tính bất biến của kiểu, quan hệ nhiều tham chiếu, sao chép phòng vệ và kiểu phần tử. Khi dùng chung trạng thái giữa nhiều luồng, hãy đánh giá tính an toàn đồng thời độc lập với từ khóa final.