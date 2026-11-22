# Giới hạn lưu, khôi phục đối tượng dựa trên tên lớp ẩn (Java 15+)

## Mục tiêu

Hiểu vì sao một **hidden class** có thể tạo và sử dụng bình thường trong JVM đang chạy, nhưng **không thể được khôi phục chỉ bằng cách lưu tên lớp**. Phân biệt việc giữ tham chiếu tới đối tượng/Class khi còn chạy với việc lưu dữ liệu để đọc ở lần chạy khác; biết giới hạn của **Class.getName()**, **Class.forName(...)**, **ClassLoader.loadClass(...)** và cơ chế **Java serialization** mặc định; áp dụng giải pháp **lưu trạng thái theo schema ổn định**, sau đó tạo lại đối tượng ở runtime nếu cần.

Hidden class được giới thiệu từ **Java 15** qua **MethodHandles.Lookup.defineHiddenClass(...)** và vẫn được hỗ trợ trong **Java 17+**. Các giới hạn về tên và cơ chế tra cứu nêu ở đây là hành vi hiện hành, không phải thủ thuật JVM cũ.

## 1. Vấn đề cốt lõi: tên hiển thị không phải định danh bền vững

Class file thông thường có **binary name** (ví dụ **demo.Message**); mã nguồn và nhiều công cụ có thể dùng tên đó để yêu cầu class loader tìm lớp. Với hidden class, JVM **không công bố một binary name để tra cứu danh nghĩa**.

Một hidden class được tạo từ bytecode bằng:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup()
        .defineHiddenClass(classBytes, true);
Class<?> hiddenClass = lookup.lookupClass();
~~~

Đây là **đoạn minh họa**, không phải chương trình chạy độc lập: classBytes phải là byte[] của class file hợp lệ và cùng package với lookup class; cần quyền Lookup thích hợp và xử lý các lỗi/ngoại lệ liên quan.

Đối với hidden class:

- **hiddenClass.isHidden()** trả về **true**.
- **hiddenClass.getName()** trả về tên mang tính mô tả runtime, có dạng gần như **tên gốc + "/" + hậu tố do JVM cấp**. Dấu **/** làm kết quả **không phải binary name**.
- **Class.forName(hiddenClass.getName())** không tìm được hidden class đó.
- **ClassLoader.loadClass(hiddenClass.getName())** cũng không tìm được nó theo cơ chế nạp lớp bằng tên.
- **hiddenClass.getCanonicalName()** trả về **null**; **hiddenClass.describeConstable()** không thể tạo mô tả danh nghĩa (trả về Optional rỗng).
- Khi đã có **Class<?>**, **MethodHandles.Lookup** hoặc **đối tượng** của lớp ẩn, chương trình vẫn có thể làm việc với nó theo các quyền hợp lệ.

**Vì vậy, getName() dùng được để hỗ trợ quan sát/debug, nhưng không phải khóa khôi phục hay ID lưu trữ.** Đừng ghi chuỗi getName() vào DB rồi dự định gọi Class.forName(...) để tái tạo kiểu dữ liệu sau khi ứng dụng khởi động lại.

## 2. Cùng bytecode nhưng không cùng lớp runtime

Mỗi lần gọi **defineHiddenClass(...)** thành công, JVM định nghĩa **một Class runtime mới**. Hai lần dùng **cùng byte[]** không biến chúng thành một kiểu dùng chung:

~~~java
Class<?> first = lookup.defineHiddenClass(bytes, true).lookupClass();
Class<?> second = lookup.defineHiddenClass(bytes, true).lookupClass();

System.out.println(first == second); // false
~~~

Đây là đoạn minh họa trong phương thức đã có biến **lookup** và **bytes**, với điều kiện bytecode/Lookup hợp lệ.

**Lý do:** identity của một lớp trong JVM không phải là “các byte trong class file giống nhau”. Hidden class mới do JVM định nghĩa là thực thể khác với hidden class trước. Nếu cùng bytes sinh ra hai lớp cùng triển khai một interface, đối tượng của cả hai có thể được xử lý thông qua interface ấy, nhưng **kiểu runtime cụ thể của chúng khác nhau**.

Điều này ảnh hưởng tới:

- **Cache theo Class<?>**: một mục cache gắn với hidden Class cũ không tự áp dụng cho hidden Class mới.
- **Trạng thái static**: mỗi hidden Class có bộ trường static riêng.
- **Reflection/MethodHandle**: handle hoặc Constructor của lớp cũ không tự trở thành handle của lớp mới.
- **Ghi log và lưu tên**: chuỗi tên runtime khác nhau không chứng minh rằng hai lớp có hành vi khác nhau; ngược lại, cùng template bytecode cũng không bảo đảm cùng Class identity.
- **Khôi phục sau restart**: sau khi JVM kết thúc, Class object và các tham chiếu runtime không còn tồn tại để dùng lại.

Một **ID nghiệp vụ** như **"message-v1"** hoặc **"pricing-rule-v2"**, do ứng dụng quản lý, phù hợp hơn tên runtime nếu cần lưu một loại đối tượng hoặc một kiểu xử lý.

## 3. Liên hệ với vòng đời và dỡ lớp

Hidden class được thiết kế hữu ích cho các lớp hỗ trợ sinh động ở runtime, không cần xuất bản tên để chương trình khác tra cứu. Theo mặc định, một hidden class **có thể được dỡ** ngay cả khi class loader định nghĩa nó vẫn còn được giữ, nếu không còn các tham chiếu thích hợp giữ lớp tồn tại.

Tùy chọn **MethodHandles.Lookup.ClassOption.STRONG** có thể yêu cầu quan hệ mạnh với class loader. Nhưng:

1. **Không có thời điểm dỡ lớp chắc chắn**: JVM/GC quyết định theo quy tắc và tình trạng tham chiếu.
2. **STRONG không khiến hidden class có binary name**: nó không làm Class.forName hoặc ClassLoader.loadClass tìm được hidden class.
3. **Giữ Class<?> hoặc instance trong một registry** có thể giúp truy cập lớp khi **cùng JVM còn chạy**; registry không phải lưu trữ bền vững qua restart.
4. **Sinh lớp lại không hồi sinh identity của lớp cũ**: chỉ tạo được một lớp mới có hành vi tương đương khi bytes và môi trường phù hợp.

Nói cách khác, **quản lý vòng đời trong bộ nhớ** và **lưu dữ liệu bền vững** là hai việc khác nhau. Không dùng tùy chọn vòng đời lớp như một cơ chế khôi phục đối tượng sau khi JVM dừng.

## 4. Giới hạn của lưu trữ dựa trên tên lớp

Giả sử một hệ thống cũ lưu hai trường:

~~~text
className = "com.example.GeneratedTask/0x0000000800abcd00"
payload   = "Xin chào"
~~~

Đây chỉ là **dữ liệu minh họa**, hậu tố không phải tên lớp ổn định.

Nếu lúc đọc dùng:

~~~java
Class<?> type = Class.forName(savedClassName);
~~~

thì với **savedClassName là tên runtime của hidden class**, thao tác không tìm được lớp đó. Điều này xảy ra **ngay cả trong cùng JVM** nếu gọi theo tên như vậy, không cần chờ lớp bị GC hoặc khởi động lại.

### Vì sao không “sửa” bằng cách bỏ hậu tố /...?

Bỏ phần hậu tố có thể thu được tên nhị phân ghi trong **class file gốc**; nó **không** trở thành tên để tìm lại hidden class đã định nghĩa. Nếu có một lớp thông thường chứa bytecode tương tự trên classpath, Class.forName có thể tìm **lớp thông thường**, nhưng đó vẫn là **Class khác** với hidden class.

### Vì sao không lưu thêm bytecode rồi coi là cùng đối tượng?

Lưu bytecode có thể giúp **tái tạo một định nghĩa lớp mới** nếu bảo đảm bytecode hợp lệ, quyền Lookup, package, class-file version và các phụ thuộc tại runtime. Tuy nhiên:

- Bytecode **không phải trạng thái của một instance**: trường dữ liệu của đối tượng cần được lưu riêng.
- Hidden class tạo lại là **Class mới**, không thể giữ đúng identity runtime cũ.
- Việc định nghĩa lại bytes phụ thuộc phiên bản JVM và môi trường tương thích.
- Cần xem bytecode đầu vào như mã thực thi có rủi ro; **không nạp bytecode không tin cậy** với quyền Lookup cao.

Vì vậy, lưu bytecode và trạng thái là một **cơ chế triển khai/khôi phục tùy biến**, không phải phép tra cứu theo tên và không được khuyến nghị cho dữ liệu nghiệp vụ thông thường nếu có thể dùng DTO/schema ổn định.

## 5. Java serialization mặc định có giải quyết được không?

**Không nên coi Serializable + ObjectOutputStream/ObjectInputStream mặc định là giải pháp khôi phục hidden class.**

Một hidden class **có thể implements java.io.Serializable**, và với các trường/điều kiện thích hợp, **ObjectOutputStream.writeObject(...) có thể ghi** instance ra byte stream. Nhưng cơ chế **ObjectInputStream.resolveClass(...) mặc định** cần tìm **Class tương ứng bằng tên** trong stream, về bản chất dùng **Class.forName(...)**. Hidden class không thể được tìm theo tên ấy, nên đọc lại bằng cơ chế mặc định **không hoạt động như với lớp thông thường**.

Trong ví dụ ở mục 7, việc ghi đối tượng hidden class thành công, nhưng **ObjectInputStream.readObject()** trong cùng JVM ném **ClassNotFoundException**. Không phải chỉ do chưa triển khai lại ứng dụng; lỗi xuất phát từ bản chất không tra cứu danh nghĩa của hidden class.

**Phân biệt một số trường hợp:**

| Trường hợp | Hành vi cần mong đợi |
| --- | --- |
| Lớp thông thường **implements Serializable**, phiên bản và classpath phù hợp | Có thể ghi/đọc bằng serialization mặc định theo hợp đồng Java serialization |
| Hidden class **không** implements Serializable | Ghi trực tiếp đối tượng bằng ObjectOutputStream thường ném **NotSerializableException** |
| Hidden class **implements Serializable** với trạng thái ghi được | Có thể ghi ra stream, nhưng **khôi phục mặc định không tìm được lớp ẩn theo tên** |
| Lưu **Class.getName()** của hidden class | Không thể dùng lại làm khóa **Class.forName** |
| Tự viết cơ chế serialization thay thế bằng **DTO/proxy/ID loại ổn định** | Có thể khôi phục dữ liệu hoặc tạo đối tượng runtime mới theo thiết kế, **không giữ Class identity cũ** |

**serialVersionUID không phải cách khắc phục**: nó giúp kiểm soát tương thích phiên bản serializable class trong cơ chế Java serialization, nhưng không biến tên hidden class thành binary name có thể tìm.

Một thiết kế tùy biến có thể dùng **writeReplace** để thay object hidden bằng một **serialization proxy** thuộc lớp thông thường, rồi dùng logic đọc tương ứng để phục hồi dữ liệu hoặc gọi factory. Tuy nhiên, nó đòi hỏi một hợp đồng lưu trữ ổn định, kiểm tra phiên bản và quản lý an toàn; không thể chỉ thêm Serializable rồi trông chờ round-trip mặc định.

**An toàn:** giải tuần tự hóa dữ liệu Java không tin cậy có rủi ro. Không dùng ObjectInputStream tùy tiện cho dữ liệu người dùng gửi lên; nên dùng định dạng dữ liệu với schema rõ, kiểm soát loại dữ liệu, kích thước và quyền truy cập.

## 6. Cách thiết kế phù hợp: lưu dữ liệu, không lưu tên lớp runtime

Với hệ thống cần lưu trạng thái bền vững, chọn một **schema độc lập với lớp được sinh**, ví dụ:

~~~text
version = 1
kind    = "message"
text    = "Xin chào"
~~~

Ở thời điểm ghi:

1. Đọc **trạng thái nghiệp vụ cần lưu** từ đối tượng dưới một interface hoặc API rõ ràng.
2. Chuyển thành **DTO/snapshot** gồm những trường ổn định và **schema version**.
3. Ghi DTO bằng một định dạng có đặc tả: JSON, CBOR, Protocol Buffers hoặc một định dạng nhị phân riêng được quản lý chặt.
4. Không ghi **hiddenClass.getName()** như thông tin bắt buộc để giải mã.

Ở thời điểm đọc:

1. Đọc dữ liệu, kiểm tra **version**, **kind**, kiểu và giới hạn kích thước.
2. Chuyển đổi schema cũ nếu có migration đã được hỗ trợ.
3. Xây dựng **DTO/đối tượng có tên** từ dữ liệu; hoặc nếu thực sự cần generated runtime class, gọi một **factory đang được triển khai** để tạo hidden class mới.
4. Gán lại trạng thái hợp lệ; không dựa vào tên hoặc Class identity runtime của lần chạy trước.

Nếu mục tiêu chỉ là lưu dữ liệu, việc tạo lại hidden class **không bắt buộc**. Có thể khôi phục trực tiếp một object thông thường hoặc DTO. Nếu hệ thống thực sự cần sinh mã runtime, factory sẽ tạo lớp mới **từ định nghĩa/cấu hình hiện hành**, rồi nhận payload đã đọc.

**Định danh bền vững nên do nghiệp vụ quản lý**, không do Class.getName() của một hidden class tình cờ được JVM tạo.

## 7. Ví dụ Java 17+ hoàn chỉnh: lưu snapshot rồi tạo lại đối tượng

Chương trình sau kiểm chứng tất cả ý chính:

- Định nghĩa hidden class từ bytecode hợp lệ của một lớp mẫu **Template**.
- Tạo hai hidden class từ cùng bytecode, nhận hai Class object khác nhau.
- Xác nhận **Class.forName** không tìm được hidden class theo getName().
- Cho Template **implements Serializable**; ghi hidden object bằng ObjectOutputStream rồi thử đọc mặc định, quan sát **ClassNotFoundException**.
- Lưu **version/kind/text** bằng **DataOutputStream** (dữ liệu độc lập với tên lớp), đọc lại bằng DataInputStream, rồi tạo **hidden instance mới** từ factory.

Lưu vào **HiddenRestoreDemo.java**:

~~~java
import java.io.*;
import java.lang.invoke.MethodHandles;
import java.nio.charset.StandardCharsets;

public class HiddenRestoreDemo {
    public interface MessageView {
        String text();
    }

    public static class Template implements MessageView, Serializable {
        @Serial private static final long serialVersionUID = 1L;
        private final String text;

        public Template(String text) {
            this.text = text;
        }

        public String text() {
            return text;
        }
    }

    public record Snapshot(int version, String kind, String text) {}

    private static byte[] templateBytes() throws IOException {
        try (InputStream in = HiddenRestoreDemo.class
                .getResourceAsStream("HiddenRestoreDemo$Template.class")) {
            if (in == null) {
                throw new IOException("Missing Template.class");
            }
            return in.readAllBytes();
        }
    }

    private static MessageView newHidden(String text) throws Exception {
        Class<?> type = MethodHandles.lookup()
                .defineHiddenClass(templateBytes(), true).lookupClass();
        return (MessageView) type.getConstructor(String.class).newInstance(text);
    }

    private static byte[] persist(Snapshot data) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(data.version());
            out.writeUTF(data.kind());
            out.writeUTF(data.text());
        }
        return buffer.toByteArray();
    }

    private static Snapshot restore(byte[] bytes) throws IOException {
        try (DataInputStream in =
                new DataInputStream(new ByteArrayInputStream(bytes))) {
            int version = in.readInt();
            String kind = in.readUTF();
            String text = in.readUTF();
            if (version != 1 || !kind.equals("message")) {
                throw new IOException("Unsupported schema");
            }
            return new Snapshot(version, kind, text);
        }
    }

    public static void main(String[] args) throws Exception {
        MessageView first = newHidden("Xin chào");
        MessageView second = newHidden("Xin chào");
        System.out.println("Hidden: " + first.getClass().isHidden());
        System.out.println("Tên chứa /: " + first.getClass().getName().contains("/"));
        System.out.println("Hai Class giống nhau: "
                + (first.getClass() == second.getClass()));

        try {
            Class.forName(first.getClass().getName());
            System.out.println("Tra theo tên: thành công");
        } catch (ClassNotFoundException ex) {
            System.out.println("Tra theo tên: ClassNotFoundException");
        }

        ByteArrayOutputStream serialized = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(serialized)) {
            out.writeObject(first);
        }
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(serialized.toByteArray()))) {
            in.readObject();
            System.out.println("ObjectInputStream: thành công");
        } catch (ClassNotFoundException ex) {
            System.out.println("ObjectInputStream: ClassNotFoundException");
        }

        Snapshot stored = new Snapshot(1, "message", first.text());
        byte[] encoded = persist(stored);
        Snapshot loaded = restore(encoded);
        MessageView recreated = newHidden(loaded.text());

        System.out.println("Schema: v" + loaded.version() + "/" + loaded.kind());
        System.out.println("Khôi phục dữ liệu: " + recreated.text());
        System.out.println("Class mới: "
                + (recreated.getClass() != first.getClass()));
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên** tại thư mục có tệp:

~~~bash
javac --release 17 -encoding UTF-8 HiddenRestoreDemo.java
java HiddenRestoreDemo
~~~

**Stdout chính xác**, đã kiểm tra bằng mã trên khi biên dịch Java 17 và chạy trên JDK 24:

~~~text
Hidden: true
Tên chứa /: true
Hai Class giống nhau: false
Tra theo tên: ClassNotFoundException
ObjectInputStream: ClassNotFoundException
Schema: v1/message
Khôi phục dữ liệu: Xin chào
Class mới: true
~~~

### Giải thích từng kết quả

1. **Hidden: true** — newHidden() dùng **Lookup.defineHiddenClass** để định nghĩa lớp mới từ bytecode của **HiddenRestoreDemo$Template.class**.
2. **Tên chứa /** — getName() trả về tên mô tả runtime không phải binary name. Chương trình in giá trị boolean, tránh phụ thuộc hậu tố do JVM sinh.
3. **Hai Class giống nhau: false** — hai lời gọi newHidden() tạo hai lớp runtime riêng biệt dù cùng bytecode và payload.
4. **Tra theo tên: ClassNotFoundException** — Class.forName không tra cứu hidden class, kể cả khi instance vẫn còn tham chiếu.
5. **ObjectInputStream: ClassNotFoundException** — vì Template implements Serializable, việc ghi đối tượng trong ví dụ thành công; nhưng đường đọc mặc định cố giải quyết class descriptor qua tên và thất bại.
6. **Schema: v1/message** — dữ liệu lưu chỉ có schema version, kind và text, **không phụ thuộc tên runtime** của hidden class.
7. **Khôi phục dữ liệu: Xin chào** — payload đọc lại được đưa cho factory, tạo đối tượng runtime có hành vi tương đương.
8. **Class mới: true** — object sau khôi phục không có Class identity cũ, dù dữ liệu nghiệp vụ vẫn đúng.

**Chi tiết triển khai ví dụ:** Interface **MessageView** là kiểu có tên ổn định, để chương trình lấy trạng thái text của object mà không cần biết tên hidden class. Class **Template** cũng là lớp có tên trong mã nguồn, nhưng **hidden class được tạo từ bytes của Template là một lớp mới**. Để ví dụ chạy độc lập, Java compiler tạo resource **HiddenRestoreDemo$Template.class** trong thư mục classpath hiện hành.

**Giới hạn của DataOutputStream.writeUTF:** Đây là ví dụ lưu snapshot nhỏ, dùng **modified UTF-8** và có giới hạn độ dài cho mỗi giá trị UTF được ghi (mỗi trường tối đa 65.535 byte mã hóa). Nó không phải giao thức chung cho file lớn hoặc một chuẩn định dạng được ứng dụng khác mặc nhiên hiểu. Trong hệ thống thật, chọn schema/encoding rõ ràng như JSON UTF-8 hoặc định dạng nhị phân có framing, giới hạn kích thước, xác minh dữ liệu và hỗ trợ migration phiên bản.

Dữ liệu đưa vào ObjectInputStream trong đoạn minh họa do **chính chương trình sinh ra**, không phải dữ liệu không tin cậy từ bên ngoài. Không dùng mẫu đọc Java serialization tùy tiện trên stream không rõ nguồn.

## 8. Cách khôi phục nào phù hợp với từng nhu cầu?

| Mục đích | Phương án nên dùng | Giới hạn cần nhớ |
| --- | --- | --- |
| Truy cập hidden object **trong cùng JVM khi còn sống** | Giữ tham chiếu instance, Class<?> hoặc một handle hợp lệ | Chỉ có giá trị khi còn tham chiếu/runtime; có thể giữ lớp lâu trong bộ nhớ |
| Lưu **trạng thái nghiệp vụ** qua restart | DTO/snapshot + schema version + kiểu dữ liệu ổn định | Cần quy tắc validate và migration |
| Tái tạo **hành vi của generated class** sau restart | Factory từ cấu hình/metadata nghiệp vụ được kiểm soát, rồi tạo hidden class mới | Class identity mới; phải tương thích bytecode, JVM và quyền Lookup |
| Dùng **tên lớp** để khôi phục như hệ thống plugin có tên | Một lớp thông thường với binary name ổn định và hợp đồng truy cập rõ ràng, nếu đúng kiến trúc | Không thể áp dụng trực tiếp cho hidden class |
| Lưu object bằng **Java native serialization** | Chỉ khi có hợp đồng serialization phù hợp và nguồn tin cậy; ưu tiên proxy/DTO rõ ràng | Hidden class không được resolve theo tên bằng ObjectInputStream mặc định |
| Muốn giảm bộ nhớ runtime | Quản lý tham chiếu và vòng đời lớp, cân nhắc tùy chọn STRONG khi thực sự cần | Không liên quan việc khôi phục đối tượng từ tên lớp |

Khi dùng **lớp thông thường**, việc lưu tên lớp cũng chưa tự bảo đảm tương thích qua nhiều phiên bản phần mềm. Đổi package, đổi tên, đổi constructor, class loader khác, thay cấu trúc class hoặc thiếu phụ thuộc đều có thể làm khôi phục thất bại. Với dữ liệu bền vững, tách **định danh nghiệp vụ** khỏi **chi tiết triển khai Java** vẫn là thiết kế an toàn hơn.

## 9. Lỗi thường gặp và cách tránh

1. **Lưu hiddenClass.getName() như khóa DB.** Tên runtime không phải binary name; Class.forName không tìm được. Lưu ID nghiệp vụ và schema version thay thế.
2. **Cho rằng cùng bytecode luôn trả về cùng Class.** Mỗi lần defineHiddenClass tạo Class runtime mới; identity, static fields và caches không được dùng chung.
3. **Nhầm giữ reference với lưu trữ vĩnh viễn.** Registry trong bộ nhớ có thể giữ Class đang chạy, nhưng mất sau restart và không được phép coi là kho dữ liệu.
4. **Dùng ClassOption.STRONG để “giữ tên lớp”.** STRONG ảnh hưởng quan hệ giữ lớp với class loader, không cấp binary name hoặc khả năng Class.forName.
5. **Thêm Serializable rồi mặc định có thể deserialize.** Hidden class không được tra cứu theo tên như lớp thường. writeObject thành công không bảo đảm readObject mặc định thành công.
6. **Nghĩ serialVersionUID sửa được ClassNotFoundException.** Nó chỉ hỗ trợ kiểm tra tương thích của class được nhận diện trong serialization; không tạo cơ chế tìm hidden class.
7. **Sửa tên lưu bằng cách xóa hậu tố /**. Tên còn lại có thể trỏ đến class mẫu thông thường chứ không phải hidden class cũ.
8. **Chỉ lưu bytecode mà không lưu trạng thái instance.** Bytecode mô tả hành vi/kiểu, không chứa giá trị trường riêng của từng object.
9. **Dùng ObjectInputStream cho dữ liệu không tin cậy.** Có thể phát sinh rủi ro bảo mật; ưu tiên dữ liệu có schema và kiểm soát loại, kích thước, nội dung.
10. **Không có schema version.** Khi yêu cầu nghiệp vụ thay đổi, dữ liệu cũ sẽ khó đọc hoặc âm thầm bị hiểu sai.
11. **Khôi phục dữ liệu thành công rồi khẳng định đã khôi phục “đúng đối tượng cũ”.** Đối tượng và Class runtime mới khác identity cũ; chỉ **trạng thái/hành vi cần thiết** được xây dựng lại.
12. **Gắn trực tiếp tên class vào giao thức truyền dữ liệu công khai.** Điều này tạo phụ thuộc vào chi tiết class loader và cách triển khai, khiến client khó tương thích dài hạn.

## 10. Tự kiểm tra

**Câu 1.** Giữ một Class<?> của hidden class trong registry có làm Class.forName(hidden.getName()) hoạt động không?  
**Đáp án:** Không. Có tham chiếu Class object không thay đổi quy tắc không tra cứu hidden class theo binary name.

**Câu 2.** Hai lần defineHiddenClass từ cùng bytecode có thể khôi phục cùng Class identity không?  
**Đáp án:** Không. Chúng tạo hai lớp runtime khác nhau. Có thể tái tạo hành vi, không lấy lại Class cũ bằng tên.

**Câu 3.** Hidden class implements Serializable thì dùng ObjectOutputStream rồi ObjectInputStream mặc định luôn round-trip được không?  
**Đáp án:** Không. Việc ghi có thể thành công, nhưng bước đọc mặc định dựa trên giải quyết tên lớp, nên không tìm được hidden class.

**Câu 4.** Thay vì lưu getName(), cần lưu gì để khôi phục dữ liệu nghiệp vụ?  
**Đáp án:** Một định danh loại nghiệp vụ ổn định (**kind**), **schema version** và **payload** đã xác thực, độc lập với lớp runtime.

**Câu 5.** Khi ứng dụng cần thực sự chạy lại generated code sau restart, việc đọc snapshot có đủ không?  
**Đáp án:** Cần factory/runtime tạo lớp mới từ cấu hình/bytecode đáng tin cậy tương thích, sau đó gán lại trạng thái hợp lệ. Class identity của lần chạy trước không được khôi phục.

## 11. Ghi nhớ

**Hidden class có thể dùng trực tiếp khi đang giữ Class/instance, nhưng không thể khôi phục chỉ từ tên lớp.** getName() của hidden class không phải binary name; Class.forName và ClassLoader.loadClass không tìm được. Native serialization mặc định cũng dựa vào khả năng nhận diện lớp theo tên, nên **không phải giải pháp lưu/khôi phục trực tiếp hidden objects**.

Đối với dữ liệu cần sống qua restart, **lưu schema ổn định thay vì tên lớp runtime**. Khi cần hành vi sinh động, tạo một hidden class mới qua factory và khôi phục **trạng thái**, không kỳ vọng hồi sinh đúng Class identity cũ.

## Tài liệu tham khảo chính thức

- Oracle, **Class — Hidden Classes, getName(), isHidden()**, Java SE 25: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html
- Oracle, **MethodHandles.Lookup.defineHiddenClass()**, Java SE 25: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Oracle, **ObjectInputStream.resolveClass()**, Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html#resolveClass(java.io.ObjectStreamClass)
- Oracle, **Serializable** và cảnh báo về deserialization, Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html
- OpenJDK, **JEP 371 — Hidden Classes**: https://openjdk.org/jeps/371
