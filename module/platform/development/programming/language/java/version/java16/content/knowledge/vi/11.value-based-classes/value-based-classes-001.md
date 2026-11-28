# JEP 390 và ý nghĩa của cảnh báo sử dụng identity trên value-based class

JEP 390 được đưa vào JDK 16 để giúp lập trình viên nhận ra một lỗi thiết kế dễ bị bỏ qua: dùng danh tính đối tượng (object identity) của những lớp được thiết kế để biểu diễn giá trị. Các lớp như **Integer**, **Optional** và **LocalDate** có thể được thay thế bằng một instance khác có cùng giá trị mà không làm thay đổi ý nghĩa của phép tính. Vì vậy, chương trình không được phụ thuộc vào việc hai biến có đang trỏ tới cùng một instance hay không.

Nguyên tắc này vẫn áp dụng trong Java hiện đại. Tài liệu Java SE 27 tiếp tục khuyến cáo không phân biệt các instance value-based class bằng **==**, không dùng chúng làm monitor để đồng bộ và không dùng chúng ở những vị trí đòi hỏi identity ổn định. JEP 390 cung cấp cảnh báo từ compiler và JVM để phát hiện một số trường hợp sử dụng sai.

## 1. Value-based class là gì?

Value-based class là một lớp có hợp đồng sử dụng dựa trên giá trị của instance thay vì danh tính của instance. Một số ví dụ trong thư viện Java là:

- Các lớp wrapper của kiểu nguyên thủy như **Integer**, **Long**, **Boolean** và **Double**.
- Các lớp **Optional**, **OptionalInt**, **OptionalLong** và **OptionalDouble**.
- Nhiều lớp trong **java.time**, chẳng hạn **LocalDate**, **LocalTime**, **LocalDateTime**, **Instant** và **Duration**.

Theo tài liệu Java SE, value-based class có những đặc điểm chính:

1. Các instance field do lớp khai báo đều là **final**. Field vẫn có thể tham chiếu tới một đối tượng mutable, vì vậy không nên suy ra rằng mọi value-based class đều bất biến sâu.
2. **equals()**, **hashCode()** và **toString()** được tính từ trạng thái của instance, không dựa trên identity.
3. Hai instance bằng nhau theo **equals()** có thể được thay thế cho nhau trong các thao tác của lớp mà không làm thay đổi hành vi quan sát được.
4. Lớp không dùng monitor của instance để đồng bộ.
5. Lớp không cung cấp cam kết rằng mỗi lần tạo instance sẽ nhận được một identity mới. Factory method có thể trả về cùng một tham chiếu cho hai lần tạo ra các giá trị bằng nhau.
6. Lớp là **final** và có cấu trúc kế thừa được giới hạn theo hợp đồng value-based.

Điểm quan trọng nhất là **identity của instance không thuộc hợp đồng mà chương trình được phép dựa vào**. JVM hiện vẫn biểu diễn nhiều lớp này bằng object reference thông thường, nhưng điều đó không tạo ra cam kết rằng mỗi giá trị luôn có một object riêng hoặc một object sẽ luôn được giữ nguyên identity.

Value-based class cũng không đồng nghĩa với bất kỳ lớp nào có **equals()** hoặc có field **final**. Hãy xem tài liệu API của lớp để biết nó có được công bố là value-based hay không.

## 2. Phân biệt value equality và object identity

Trong Java, hai phép so sánh sau trả lời hai câu hỏi khác nhau:

- **==** với hai reference kiểm tra chúng có trỏ tới cùng một object hay không.
- **equals()** kiểm tra hai object có được xem là bằng nhau theo hợp đồng của lớp hay không.

Với value-based class, chương trình cần quan tâm đến giá trị. Ví dụ:

~~~java
Integer first = Integer.valueOf(1000);
Integer second = Integer.valueOf(1000);

System.out.println(first.equals(second)); // true
System.out.println(first == second);      // Không có cam kết về kết quả
~~~

Hai biến có cùng giá trị số nên **equals()** trả về **true**. Kết quả của **==** phụ thuộc vào cách runtime tạo hoặc tái sử dụng instance. API không cam kết rằng hai lời gọi factory sẽ tạo hai object khác nhau, cũng không cam kết chúng phải dùng chung một object. Vì vậy, không dùng kết quả của **==** để quyết định hai giá trị này có bằng nhau hay không.

Khi cần so sánh có xử lý cả **null**, có thể dùng **Objects.equals()**:

~~~java
import java.util.Objects;

Integer first = Integer.valueOf(1000);
Integer second = Integer.valueOf(1000);

if (Objects.equals(first, second)) {
    System.out.println("Hai giá trị bằng nhau");
}
~~~

So sánh với **null** vẫn hợp lệ:

~~~java
if (first == null) {
    System.out.println("Chưa có giá trị");
}
~~~

Ở đây **==** chỉ kiểm tra tham chiếu có phải **null** hay không, không dùng identity để phân biệt hai instance value-based.

### Phân biệt hashCode và identity hash code

**hashCode()** thông thường của value-based class được tính từ giá trị. Đây là hành vi cần thiết để các collection dựa trên **equals()** và **hashCode()** hoạt động đúng.

Ngược lại, **System.identityHashCode(object)** lấy identity hash code của object, bỏ qua cách lớp ghi đè **hashCode()**. Không dùng kết quả này để nhận diện hoặc phân biệt các instance value-based.

~~~java
Integer amount = Integer.valueOf(500);

int valueHash = amount.hashCode();
int identityHash = System.identityHashCode(amount);
~~~

Hai giá trị trên có mục đích khác nhau. Với value-based class, hãy dùng **hashCode()** thông thường khi làm việc với giá trị; tránh xây dựng logic dựa trên identity hash code.

## 3. Vì sao không nên synchronized trên value-based class?

Mỗi object Java có một intrinsic monitor, có thể được dùng với câu lệnh **synchronized**, **wait()** và **notify()**. Cách đồng bộ này chỉ đúng khi chương trình kiểm soát được object làm khóa và bảo đảm các luồng cần phối hợp sử dụng cùng một khóa.

Value-based class không bảo đảm điều đó. Factory method có thể tái sử dụng instance, nên những đoạn code độc lập có thể vô tình đồng bộ trên cùng một monitor. Runtime cũng được phép thay đổi cách cấp phát hoặc tái sử dụng instance trong các phiên bản tương lai.

Ví dụ sau là cách dùng không an toàn:

~~~java
public class Counter {
    private static final Integer LOCK = Integer.valueOf(1);
    private int value;

    public void increment() {
        synchronized (LOCK) {
            value++;
        }
    }
}
~~~

**Integer** là value-based class. Giá trị được tạo qua factory có thể dùng chung instance với những đoạn code khác. Khi đó, các thành phần không liên quan có thể tranh chấp cùng monitor. Ngược lại, nếu chương trình giả định mỗi lần tạo một giá trị bằng nhau sẽ có một monitor riêng, giả định đó cũng không được API bảo đảm.

Hãy dùng một object khóa chuyên biệt có identity ổn định và được kiểm soát bởi lớp:

~~~java
public class Counter {
    private final Object lock = new Object();
    private int value;

    public void increment() {
        synchronized (lock) {
            value++;
        }
    }

    public int getValue() {
        synchronized (lock) {
            return value;
        }
    }
}
~~~

Với khóa dùng chung giữa các instance, có thể khai báo một object khóa riêng tư dạng **private static final Object**. Không thay khóa bằng **Integer**, **Long**, **Boolean**, **Optional** hoặc một value-based class khác.

Quy tắc tương tự áp dụng cho **wait()**, **notify()** và **notifyAll()**, vì các phương thức này gắn với monitor của object. Nếu cần phối hợp luồng, hãy dùng khóa chuyên biệt hoặc các công cụ đồng bộ cấp cao như **ReentrantLock**, **BlockingQueue**, **CountDownLatch** hay những API phù hợp trong **java.util.concurrent**.

## 4. JEP 390 đưa ra những cảnh báo nào?

JEP 390 được phát hành cùng Java 16 và có ba phần đáng chú ý đối với chủ đề identity:

- JDK đánh dấu các lớp value-based trong thư viện nền tảng bằng annotation nội bộ **jdk.internal.ValueBased**. Annotation này giúp công cụ của JDK nhận diện những lớp cần tuân theo hợp đồng value-based; đây không phải API công khai để ứng dụng import và sử dụng.
- **javac** bổ sung cảnh báo khi phát hiện một số trường hợp dùng instance value-based ở vị trí đòi hỏi identity, đặc biệt là đồng bộ trên instance.
- HotSpot bổ sung khả năng chẩn đoán lúc chạy khi chương trình đồng bộ trên instance value-based.

Cảnh báo không có nghĩa mọi đoạn code đang chạy sẽ lập tức ném exception. Vấn đề là chương trình đang dựa vào một hành vi mà API không bảo đảm. Tài liệu Java SE hiện hành nói rõ hành vi liên quan tới identity có thể thay đổi trong phiên bản tương lai; ví dụ, thao tác đồng bộ có thể thất bại.

### Bật cảnh báo từ javac

Với JDK 27, nhóm lint hiện hành là **identity**:

~~~bash
javac -Xlint:identity -d out src/example/Main.java
~~~

Tài liệu **javac** của JDK 27 cho biết **identity** cảnh báo việc sử dụng value-based class ở nơi cần identity class và nhóm này được bật mặc định. Tên **synchronization** trước đây vẫn được giữ như alias có cùng tác dụng, nhưng đã deprecated; khi cấu hình mới, hãy dùng **-Xlint:identity**.

Có thể yêu cầu compiler coi cảnh báo thuộc nhóm này là lỗi để ngăn code mới đưa thêm cách dùng identity không an toàn vào dự án:

~~~bash
javac -Xlint:identity -Werror:identity -d out src/example/Main.java
~~~

Compiler chỉ phát hiện được những trường hợp nó nhận diện được từ mã nguồn và thông tin kiểu. Vì vậy, việc không thấy cảnh báo không chứng minh rằng chương trình không có logic phụ thuộc identity.

### Chẩn đoán đồng bộ lúc chạy trên HotSpot

Khi cần tìm đường chạy thực tế có đồng bộ trên value-based class, HotSpot cung cấp tùy chọn chẩn đoán:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:DiagnoseSyncOnValueBasedClasses=2 -jar app.jar
~~~

Ở chế độ **2**, JVM ghi thông báo khi phát hiện đồng bộ trên instance value-based. Chế độ **1** khiến JVM kết thúc bằng lỗi nghiêm trọng khi phát hiện trường hợp này; chế độ mặc định **0** tắt chẩn đoán. Đây là tùy chọn chẩn đoán của HotSpot, hữu ích khi kiểm tra hoặc di trú ứng dụng; không nên xem nó là cơ chế đồng bộ hay giải pháp thay thế cho việc sửa code.

## 5. Những vị trí khác cần tránh phụ thuộc identity

Ngoài **==** và **synchronized**, hãy kiểm tra các trường hợp sau:

| Cách sử dụng | Vấn đề | Cách xử lý |
| --- | --- | --- |
| So sánh hai instance bằng **==** | Dựa vào việc hai biến có trỏ tới cùng object | Dùng **equals()** hoặc **Objects.equals()** |
| Gọi **System.identityHashCode()** | Dựa vào identity hash code | Dùng **hashCode()** theo giá trị |
| Dùng value-based instance làm khóa trong **IdentityHashMap** | **IdentityHashMap** so sánh khóa bằng **==** | Dùng **HashMap** nếu muốn so sánh theo **equals()** |
| Dùng instance làm monitor hoặc gọi **wait()**/**notify()** trên instance | Không bảo đảm quyền sở hữu độc quyền đối với monitor | Dùng object khóa riêng hoặc API đồng bộ phù hợp |
| Dùng instance làm referent của **WeakReference**, **SoftReference** hoặc **PhantomReference** | Identity của referent không đáng tin cậy theo hợp đồng value-based | Chọn một object có identity ổn định làm referent |

**HashMap** và **HashSet** phù hợp với value-based class vì chúng dựa trên **equals()** và **hashCode()**. **IdentityHashMap** có mục đích khác: nó cố ý so sánh bằng identity. Chỉ dùng collection này khi thuật toán thực sự cần phân biệt object theo identity và các khóa có hợp đồng identity phù hợp.

Tài liệu Java SE 27 cũng khuyến cáo không dùng instance value-based làm referent của các reference object trong **java.lang.ref**, vì các instance này không có identity đáng tin cậy. Đây là một trường hợp dễ bị bỏ sót khi thiết kế cache hoặc cơ chế theo dõi object.

## 6. Cách đọc và xử lý cảnh báo trong dự án

Khi gặp cảnh báo liên quan tới value-based class, hãy xác định đoạn code đang cần giá trị hay cần identity:

1. Nếu cần kiểm tra hai giá trị bằng nhau, chuyển sang **equals()** hoặc **Objects.equals()**.
2. Nếu cần khóa để bảo vệ trạng thái dùng chung, tạo một object khóa riêng và giữ quyền sở hữu khóa trong lớp.
3. Nếu cần collection theo giá trị, dùng collection dựa trên **equals()** và **hashCode()**.
4. Nếu code cần identity thực sự, thiết kế một object có identity ổn định và dùng object đó cho mục đích này.
5. Kiểm tra cả code gọi thư viện, callback và code đồng bộ gián tiếp; cảnh báo có thể xuất phát từ một lớp khác trong ứng dụng.

Không nên tắt cảnh báo hoặc thêm **@SuppressWarnings** chỉ để làm sạch kết quả build. Chỉ cân nhắc suppress khi đã xác minh được hợp đồng của đoạn code và có lý do kỹ thuật rõ ràng; với value-based class, cách xử lý thông thường là thay đổi đối tượng được dùng cho thao tác identity.

## 7. Kết luận

JEP 390 nhắc lập trình viên rằng một giá trị và object đang chứa giá trị đó là hai khái niệm khác nhau. Với value-based class, hợp đồng API bảo đảm ý nghĩa của giá trị, không bảo đảm identity của từng instance. Do đó, hãy so sánh bằng **equals()**, dùng **hashCode()** theo giá trị, tránh identity hash code và không dùng instance làm monitor hoặc referent của reference object.

Trong JDK 27, hãy chú ý cảnh báo lint **identity**; đây là tên hiện hành thay cho alias **synchronization** đã deprecated. Khi cần kiểm tra thêm các đường chạy thực tế, có thể dùng tùy chọn chẩn đoán của HotSpot trong môi trường kiểm thử.

## Tài liệu tham khảo

- [JEP 390: Warnings for Value-Based Classes](https://openjdk.org/jeps/390)
- [Value-based Classes — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/doc-files/ValueBased.html)
- [The javac Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [JDK 16 Release Notes — JEP 390](https://www.oracle.com/java/technologies/javase/16-relnote-issues.html)
- [HotSpot runtime flags — OpenJDK source](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/globals.hpp)

