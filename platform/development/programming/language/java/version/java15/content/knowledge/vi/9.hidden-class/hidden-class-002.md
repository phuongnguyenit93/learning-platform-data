# Phân biệt lớp ẩn với lớp thông thường và lớp vô danh (Java 15+)

## Mục tiêu

Phân biệt chính xác ba khái niệm: **lớp thông thường (ordinary/named class)**, **lớp vô danh (anonymous class trong cú pháp Java)** và **lớp ẩn (hidden class ở cấp JVM)**. Hiểu cách chúng được tạo, định danh, nạp, truy xuất và sử dụng; biết vì sao tên gọi “vô danh” không đồng nghĩa với “ẩn”; thực hành API **MethodHandles.Lookup.defineHiddenClass(...)** cùng **Class.isHidden()** và **Class.isAnonymousClass()**.

Hidden class được giới thiệu trong **Java 15** và tiếp tục là API được hỗ trợ trong **Java 17+**. Ví dụ dùng các API Java chính thức, không dựa vào các cơ chế nội bộ hoặc API đã lỗi thời.

## 1. Ba khái niệm nhìn từ hai tầng khác nhau

**Lớp thông thường** có khai báo lớp với tên trong mã nguồn Java. Trình biên dịch tạo bytecode cho lớp; khi ứng dụng chạy, JVM có thể nạp lớp bằng cơ chế nạp lớp thông thường. Lớp có **binary name** để các lớp khác có thể tham chiếu theo tên.

~~~java
class Greeter {
    void greet() {
        System.out.println("Xin chào!");
    }
}
~~~

Đây là một khai báo lớp thông thường, dùng để minh họa. Trong mã gọi hợp lệ, có thể viết **new Greeter()** hoặc truy cập **Greeter.class**.

**Lớp vô danh** được khai báo bằng **anonymous class expression** trong Java. Nó không có tên khai báo do lập trình viên đặt, thường dùng để tạo nhanh một đối tượng kế thừa lớp hoặc triển khai interface tại chỗ.

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("Chạy từ lớp vô danh");
    }
};
~~~

Lớp vô danh **vẫn là một lớp bình thường đối với cơ chế tên và nạp lớp của JVM**. Trình biên dịch thường tạo bytecode của nó trong một class file riêng với một tên nhị phân được sinh tự động, ví dụ có phần hậu tố dạng **$1**. Tên sinh ra là chi tiết triển khai, không nên sử dụng như API ổn định. Đặc tính quan trọng là **task.getClass().isAnonymousClass() trả về true**, còn **task.getClass().isHidden() trả về false** trong trường hợp lớp vô danh thông thường này.

**Lớp ẩn (hidden class)** là một loại lớp được **định nghĩa tại thời điểm chạy** từ bytecode bằng API **MethodHandles.Lookup.defineHiddenClass(...)**. Điểm đặc trưng không phải “thiếu tên trong mã Java”, mà là nó **không có binary name dùng để tra cứu hoặc tham chiếu danh nghĩa** như lớp thông thường.

Vì vậy, **Class.forName(...)** và **ClassLoader.loadClass(...)** không thể tra cứu một hidden class theo tên. Tuy nhiên, khi đã giữ **Class<?>**, **MethodHandles.Lookup**, hoặc đối tượng của nó, ứng dụng vẫn có thể tương tác với hidden class theo các quyền truy cập hợp lệ. Hidden class **không phải** công cụ bảo mật để giữ bí mật logic.

## 2. Bảng so sánh trọng tâm

| Tiêu chí | Lớp thông thường | Lớp vô danh trong Java | Hidden class |
| --- | --- | --- | --- |
| Cách tạo điển hình | Khai báo **class Greeter** | Biểu thức **new Runnable() { ... }** | **Lookup.defineHiddenClass(byte[], ...)** khi chạy |
| Tên ở cấp mã nguồn | Có tên khai báo | Không có tên khai báo riêng | Không khai báo bằng từ khóa đặc biệt trong mã Java |
| Tên ở cấp JVM | Có **binary name** | Có binary name được trình biên dịch sinh | **Không có binary name** dùng để tra cứu danh nghĩa |
| Có thể tham chiếu trực tiếp trong Java source theo tên lớp | Có, trong phạm vi truy cập | Không dùng tên riêng do lập trình viên đặt; thường dùng qua kiểu cha/interface | Không thể đặt trực tiếp tên hidden class vào mã nguồn như một kiểu có tên |
| **Class.isHidden()** | false | false đối với lớp vô danh thông thường | true |
| **Class.isAnonymousClass()** | false ở lớp có tên thông thường | true | Không dùng phương thức này để xác định hidden; dùng **isHidden()** |
| **Class.forName(...)** theo tên của lớp | Có thể, nếu lớp có trên đường nạp và truy cập phù hợp | Có thể có tên nhị phân do compiler sinh, nhưng không nên dựa vào tên này | **Không thể tìm theo tên của hidden class** |
| Vai trò điển hình | Kiểu dữ liệu và logic ứng dụng dùng lâu dài | Hành vi một lần tại vị trí dùng | Runtime/framework tạo lớp hỗ trợ nội bộ |

**Hai tiêu chí độc lập:** “vô danh” nói về **cú pháp khai báo lớp trong Java**; “ẩn” nói về **cách JVM định nghĩa và cho phép tìm lớp**. Một anonymous class trong mã nguồn **không tự trở thành hidden class** chỉ vì người viết không đặt tên cho nó.

## 3. Vì sao JVM có hidden class?

Nhiều thư viện và runtime cần tạo **rất nhiều lớp hỗ trợ** tại thời điểm chạy, ví dụ khi sinh bộ thích ứng cho lời gọi động, triển khai các cơ chế runtime hoặc sinh mã. Các lớp hỗ trợ ấy thường không cần được ứng dụng khác tra cứu lại qua tên nhị phân. Việc đưa mọi lớp sinh động vào cùng cơ chế nạp lớp thông thường có thể khiến phạm vi tên và vòng đời lớp khó quản lý.

Hidden class giải quyết yêu cầu: runtime định nghĩa một lớp từ **class-file bytes** và nhận lại **Lookup** trên lớp vừa tạo, mà không xuất bản nó như một lớp có tên có thể tìm bằng **Class.forName**.

Các điểm cần hiểu:

1. **Không tra cứu danh nghĩa:** tên từ **Class.getName()** của hidden class có thể chứa dấu **/** cùng hậu tố JVM, nên không phải binary name hợp lệ để gọi Class.forName.
2. **Có Class object thật:** hidden class có **Class<?>** và các thành viên, có thể tạo thể hiện, gọi phương thức và thực hiện reflection hoặc method handles nếu có quyền thích hợp.
3. **Có thể triển khai interface:** một hidden class có thể cung cấp đối tượng qua interface ổn định, ví dụ **Runnable** trong chương trình ở dưới.
4. **Linh hoạt về vòng đời:** mặc định, hidden class có thể được dỡ khỏi JVM ngay cả khi class loader liên quan vẫn còn sống, **nếu các tham chiếu thích hợp không còn giữ lớp**. Đây là khả năng của JVM, không phải cam kết Garbage Collector sẽ dỡ ngay tại một thời điểm xác định.
5. **Không phải mọi class sinh động đều hidden:** thư viện vẫn có thể chọn định nghĩa các lớp thông thường theo nhu cầu sử dụng và thiết kế của mình.

**Không đồng nhất hidden class với lambda.** JVM hoặc runtime có thể dùng lớp ẩn trong quá trình triển khai một số cơ chế ngôn ngữ, nhưng **cách triển khai lambda là chi tiết runtime**, không phải quy tắc rằng mọi lambda phải là một hidden class. Để kiểm tra một Class cụ thể, dùng **Class.isHidden()** thay vì đoán theo cú pháp.

## 4. Tạo hidden class bằng API hiện hành

API chính là:

~~~java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(classBytes, true);
Class<?> hiddenClass = hiddenLookup.lookupClass();
~~~

Đoạn trên minh họa **hai câu lệnh** bên trong phương thức có xử lý ngoại lệ và biến **classBytes** kiểu byte[] chứa một class file hợp lệ. Đó chưa phải một chương trình độc lập.

**Ý nghĩa từng thành phần:**

- **MethodHandles.lookup()** lấy đối tượng Lookup gắn với ngữ cảnh truy cập của lớp gọi. Khi định nghĩa hidden class, Lookup phải có quyền phù hợp, gồm quyền truy cập đầy đủ theo hợp đồng API; bytecode phải thuộc **cùng package** với lớp của Lookup.
- **defineHiddenClass(classBytes, true)** định nghĩa một lớp ẩn từ byte[] ở thời điểm chạy. Tham số **true** yêu cầu **khởi tạo** lớp; nếu là false, việc khởi tạo có thể được hoãn theo quy tắc JVM.
- **lookupClass()** trả về **Class<?>** của lớp ẩn vừa tạo.
- **Class.isHidden()** xác nhận tính chất hidden của Class đó.

Phương thức có thể ném **IllegalAccessException** nếu Lookup thiếu quyền; bytecode không hợp lệ hoặc không thỏa điều kiện có thể phát sinh những lỗi như **ClassFormatError**, **IllegalArgumentException**, **VerifyError** hoặc **LinkageError**. Trong ứng dụng thực, bytecode cần được tạo và kiểm soát bởi thành phần tin cậy; không đưa bytecode nhận tùy ý từ người dùng vào cơ chế này.

**Tùy chọn hiện hành:** Khi cần lớp ẩn được xem là **nestmate** của lớp Lookup để hỗ trợ truy cập private theo cơ chế nest, API có **MethodHandles.Lookup.ClassOption.NESTMATE**. Khi cần hidden class có quan hệ mạnh với class loader về khả năng dỡ lớp, dùng **ClassOption.STRONG**. Ví dụ cơ bản ở dưới **không dùng hai tùy chọn này** vì không cần truy cập private hoặc điều chỉnh vòng đời.

## 5. Ví dụ Java 17+ hoàn chỉnh

Ví dụ so sánh cả ba loại lớp theo API phản chiếu. Để không phải viết một bộ sinh bytecode riêng, chương trình **đọc bytecode đã biên dịch** của lớp Template và dùng bytecode đó định nghĩa **một hidden class mới, khác với Template.class**. Đây là kỹ thuật minh họa; các framework thường tạo hoặc biến đổi bytecode bằng thành phần chuyên dụng.

Lưu toàn bộ mã sau vào tệp **ClassKindsDemo.java**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandles;

public class ClassKindsDemo {
    static class Ordinary implements Runnable {
        public void run() {
            System.out.println("Ordinary chạy");
        }
    }

    public static class Template implements Runnable {
        public void run() {
            System.out.println("Hidden chạy");
        }
    }

    public static void main(String[] args) throws Exception {
        Runnable ordinary = new Ordinary();
        Runnable anonymous = new Runnable() {
            public void run() {
                System.out.println("Anonymous chạy");
            }
        };

        byte[] bytes;
        try (InputStream input = ClassKindsDemo.class
                .getResourceAsStream("ClassKindsDemo$Template.class")) {
            if (input == null) {
                throw new IOException("Không tìm thấy bytecode của Template");
            }
            bytes = input.readAllBytes();
        }

        MethodHandles.Lookup lookup =
                MethodHandles.lookup().defineHiddenClass(bytes, true);
        Class<?> hiddenClass = lookup.lookupClass();
        Runnable hidden = (Runnable)
                hiddenClass.getDeclaredConstructor().newInstance();

        System.out.println("Ordinary: hidden=" + ordinary.getClass().isHidden()
                + ", anonymous=" + ordinary.getClass().isAnonymousClass());
        System.out.println("Anonymous: hidden=" + anonymous.getClass().isHidden()
                + ", anonymous=" + anonymous.getClass().isAnonymousClass());
        System.out.println("Hidden: hidden=" + hiddenClass.isHidden()
                + ", anonymous=" + hiddenClass.isAnonymousClass());
        System.out.println("Hidden có / trong getName(): "
                + hiddenClass.getName().contains("/"));
        System.out.println("Khác Template.class: "
                + (hiddenClass != Template.class));

        try {
            Class.forName(hiddenClass.getName());
            System.out.println("Class.forName: tìm thấy");
        } catch (ClassNotFoundException ex) {
            System.out.println("Class.forName: không tìm thấy hidden class");
        }

        ordinary.run();
        anonymous.run();
        hidden.run();
    }
}
~~~

**Biên dịch và chạy** tại thư mục chứa tệp, với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 ClassKindsDemo.java
java ClassKindsDemo
~~~

Trình biên dịch tạo các tệp class cho lớp chính và các lớp lồng bên trong, bao gồm **ClassKindsDemo$Template.class**. Khi chạy bằng classpath là thư mục hiện hành, lệnh **getResourceAsStream(...)** có thể tìm thấy tệp class của Template. Nếu chạy trong JAR hoặc hệ thống build khác, cần bảo đảm bytecode mẫu tương ứng có trên classpath.

**Stdout chính xác** (đã biên dịch ở mức Java 17 và chạy thành công trên JDK 24):

~~~text
Ordinary: hidden=false, anonymous=false
Anonymous: hidden=false, anonymous=true
Hidden: hidden=true, anonymous=false
Hidden có / trong getName(): true
Khác Template.class: true
Class.forName: không tìm thấy hidden class
Ordinary chạy
Anonymous chạy
Hidden chạy
~~~

**Phân tích kết quả:**

- **Ordinary:** lớp có tên; hai phép kiểm tra đều false vì không phải lớp vô danh hoặc hidden class.
- **Anonymous:** được viết bằng **new Runnable() { ... }**, nên **isAnonymousClass()** true; **isHidden()** false.
- **Hidden:** được định nghĩa bằng **defineHiddenClass**, nên **isHidden()** true. Trong ví dụ này **isAnonymousClass()** false; hai phép kiểm tra xem xét **hai khía cạnh khác nhau**.
- **Tên chứa dấu /** được kiểm tra bằng boolean để không phụ thuộc vào hậu tố do JVM sinh. Không nên hardcode một tên hidden class vào chương trình.
- **Khác Template.class:** cùng sử dụng bytecode gốc nhưng **hai Class object biểu diễn hai lớp runtime khác nhau**. Hidden class không phải “đổi cờ” trên đối tượng Class của Template.
- **Class.forName:** không tìm thấy hidden class qua tên; điều đó **không ngăn** tạo thể hiện và gọi **hidden.run()** qua giao diện Runnable. Cả ba đối tượng đều chạy phương thức run bình thường.

## 6. Phân biệt kỹ hơn lớp vô danh và lớp ẩn

### Khác nhau ở cách khai báo

Lớp vô danh được tạo bằng cú pháp Java quen thuộc:

~~~java
Runnable action = new Runnable() {
    @Override
    public void run() {
        System.out.println("Action");
    }
};
~~~

Đây là **biểu thức tạo đối tượng của một anonymous class**. Trình biên dịch quyết định tên và class file tương ứng. Lập trình viên thường giữ tham chiếu dưới kiểu **Runnable** và không cần quan tâm tên lớp thực tế.

Hidden class **không có cú pháp khai báo riêng bằng một từ khóa class ẩn** trong Java source. Nó được tạo bằng API runtime nhận bytecode. Do đó, nếu chỉ cần viết một callback nhỏ trong ứng dụng, không cần dựng bytecode rồi gọi defineHiddenClass.

### Khác nhau ở tên lớp

Với lớp vô danh, gọi **getClass().getName()** có thể thấy một tên được compiler tạo như **Outer$1**. Tên này là tên nhị phân của lớp ở runtime, nhưng **không phải một kiểu có tên để viết trực tiếp trong mã nguồn**. Một lớp vô danh Java bình thường vẫn có thể được tải theo cơ chế lớp thông thường.

Với hidden class, **getName() không trả về binary name** phù hợp cho việc tìm lớp qua Class.forName. Đây là ràng buộc chủ đích của hidden class, không phải chỉ do tên “khó đọc”. Đừng gọi Class.forName(hidden.getName()) và xem thất bại như lỗi cấu hình classpath.

### Khác nhau ở mục đích

- **Anonymous class**: thuận tiện khi lập trình viên muốn tạo một biến thể hành vi tại chỗ, ví dụ một handler hoặc Runnable. Với interface hàm đơn, lambda đôi khi ngắn gọn hơn; chọn theo yêu cầu cụ thể.
- **Hidden class**: thuận tiện cho framework/runtime cần sinh nhiều định nghĩa lớp hỗ trợ, không muốn xuất bản các lớp đó để mọi nơi tra cứu theo tên.
- **Ordinary class**: phù hợp cho kiểu dữ liệu hay thành phần ứng dụng có tên, được nhiều nơi tham chiếu trực tiếp và cần API rõ ràng.

## 7. Lưu ý về vòng đời, quyền truy cập và công cụ

**Vòng đời:** Khác với lớp thông thường có quan hệ mạnh với class loader, hidden class theo mặc định có thể được JVM dỡ trong khi class loader còn tồn tại, nếu không còn tham chiếu giữ nó. Tùy chọn **STRONG** thay đổi mối quan hệ này. Việc dỡ lớp phụ thuộc garbage collection và **không thể dự đoán thời điểm chính xác**. Không dùng hidden class như cơ chế bắt buộc giải phóng bộ nhớ ngay.

**Quyền truy cập:** Ẩn tên lớp không tự cho phép vượt qua quyền Java. Lookup, package, module và quy tắc truy cập vẫn quan trọng. **NESTMATE** chỉ cấp quyền theo quan hệ nestmate khi được cấu hình hợp lệ; nó không phải lệnh cho phép bất kỳ lớp nào truy cập mọi thành viên private của mọi lớp khác.

**Phản chiếu và điều tra lỗi:** Khi nắm Class object, có thể xem metadata, phương thức, constructor và tương tác theo quyền truy cập. Stack trace hoặc tên runtime có thể hiển thị tên hidden class cùng hậu tố đặc biệt. Đừng giả định tên lớp luôn là binary name hoặc luôn ánh xạ được sang tệp nguồn trên đĩa.

**Triển khai:** Trong ví dụ, bytecode của Template đã có sẵn do javac tạo. Trong thực tế, bytecode có thể sinh tại runtime; nhưng dù xuất phát từ đâu, **defineHiddenClass** phải nhận byte[] biểu diễn class hợp lệ và thỏa các điều kiện bảo mật/truy cập của Lookup.

## 8. Lỗi hiểu nhầm thường gặp

1. **“Lớp vô danh chính là hidden class.”** Sai. Anonymous class là một cấu trúc cú pháp Java; hidden class là cơ chế định nghĩa lớp của JVM. Kiểm tra bằng **isAnonymousClass()** và **isHidden()**.
2. **“Hidden class hoàn toàn không có tên nào.”** Nó vẫn có biểu diễn tên do **Class.getName()** trả về; vấn đề là tên đó **không phải binary name có thể dùng để tra cứu theo Class.forName**.
3. **“Class.forName không tìm thấy nghĩa là không thể gọi được phương thức.”** Sai. Nếu có **Class object**, MethodHandle hoặc đối tượng dưới một interface, chương trình vẫn tương tác được với lớp ẩn theo quyền hợp lệ.
4. **“Đọc class bytes của Template là biến Template thành hidden class.”** Sai. defineHiddenClass định nghĩa **lớp mới**. Template.class và hiddenClass là **hai Class object khác nhau**.
5. **“Mọi lambda đều bắt buộc là hidden class.”** Không có đảm bảo ngôn ngữ như vậy; cơ chế sinh lớp của runtime có thể thay đổi. Không dựa vào chi tiết triển khai lambda.
6. **“Hidden class giúp che giấu code khỏi mọi công cụ hoặc mang lại sandbox bảo mật.”** Sai. Không tìm qua tên nhị phân không tương đương bí mật mã hoặc cách ly quyền truy cập.
7. **“Hidden class sẽ được GC ngay khi xong một lần gọi.”** Không có đảm bảo thời điểm dỡ lớp. Nếu còn tham chiếu tới Class, object hoặc metadata liên quan, lớp có thể còn tồn tại.
8. **“Có thể tạo hidden class từ bytecode tùy ý không cần quyền hay xác minh.”** API kiểm tra quyền của Lookup, package và cấu trúc bytecode. Không nên nạp bytecode không đáng tin cậy như một giải pháp mở rộng tiện tay.
9. **“Class.isAnonymousClass() là cách nhận diện lớp ẩn.”** Sai mục đích. Dùng **Class.isHidden()** để xác định hidden class; tính chất anonymous class là vấn đề khác.
10. **“Lớp thông thường luôn phải là lớp top-level.”** Lớp có tên có thể là lớp lồng; ví dụ **Ordinary** và **Template** đều là lớp lồng có tên trong ClassKindsDemo, không phải anonymous class.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Một đối tượng được tạo bằng **new Runnable() { ... }**, không qua defineHiddenClass. Đặc điểm nào đúng?  
**Đáp án:** Đây là anonymous class; trong trường hợp thông thường **isAnonymousClass() = true** và **isHidden() = false**.

**Câu 2.** Hidden class có thể triển khai Runnable và chạy run() không?  
**Đáp án:** Có. Hidden class là lớp runtime thực sự; ví dụ trên dùng interface Runnable để gọi run() thành công.

**Câu 3.** Vì sao Class.forName(hiddenClass.getName()) thất bại?  
**Đáp án:** Vì hidden class không có binary name có thể tra cứu bằng cơ chế Class.forName; việc giữ Class object vẫn cho phép tương tác theo quyền hợp lệ.

**Câu 4.** Cần kiểm tra liệu Class<?> có phải hidden class không, dùng API nào?  
**Đáp án:** **Class.isHidden()**.

**Câu 5.** Khi viết một handler ngắn trong mã nguồn, có nên tự sinh hidden class không?  
**Đáp án:** Thông thường không cần. Dùng lớp có tên, anonymous class hoặc lambda phù hợp với yêu cầu; hidden class phục vụ nhu cầu sinh lớp ở runtime đặc thù hơn.

## 10. Ghi nhớ

**Lớp thông thường có tên, có thể được tham chiếu theo kiểu có tên. Lớp vô danh không có tên khai báo trong Java source nhưng vẫn là lớp bình thường ở cấp JVM, được compiler gán binary name. Hidden class được định nghĩa bằng API runtime và không có binary name có thể tìm qua Class.forName hoặc ClassLoader.loadClass.**

Hai kiểm tra có ý nghĩa riêng: **Class.isAnonymousClass()** phân biệt anonymous class; **Class.isHidden()** xác nhận hidden class. Với ứng dụng thông thường, dùng các cấu trúc Java quen thuộc; chỉ dùng **Lookup.defineHiddenClass** khi thực sự cần định nghĩa lớp runtime mà không xuất bản danh tính theo tên.

## Tài liệu tham khảo chính thức

- Oracle, **Class - Hidden Classes**, Java SE 25: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html
- Oracle, **MethodHandles.Lookup.defineHiddenClass(...)**, Java SE 25: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Oracle, **MethodHandles.Lookup.ClassOption**, Java SE 25: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html
- OpenJDK, **JEP 371: Hidden Classes**: https://openjdk.org/jeps/371
