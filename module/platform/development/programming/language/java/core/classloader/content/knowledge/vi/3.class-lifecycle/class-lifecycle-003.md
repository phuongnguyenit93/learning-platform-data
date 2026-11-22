# Nạp các lớp cha và interface cha cần thiết trong vòng đời lớp Java

## 1. Mục tiêu: vì sao phải nạp kiểu cha trước khi lớp con hoạt động?

Khi JVM tạo một định nghĩa runtime cho lớp Java, việc tìm thấy file `.class` của lớp đó mới chỉ là bước đầu. JVM còn phải xác lập **quan hệ kế thừa**: lớp này có lớp cha trực tiếp nào (`extends`), có những interface cha trực tiếp nào (`implements` hoặc `extends` giữa các interface), và chúng có hợp lệ hay không. Những kiểu cha cần thiết phải được nạp theo các quy tắc của JVM trước khi định nghĩa lớp con được tạo thành công.

Ví dụ:

```java
interface Auditable {}
interface Identified extends Auditable {}
class Entity {}
class Customer extends Entity implements Identified {}
```

Khi nạp `Customer`, JVM phải xử lý lớp cha trực tiếp `Entity` và interface trực tiếp `Identified`. Để nạp `Identified`, JVM cũng phải xử lý interface cha `Auditable`. Các quan hệ này tạo thành một đồ thị phụ thuộc kiểu, không chỉ là quan hệ giữa các file nguồn.

Cần phân biệt từ đầu:

- **Nạp (loading):** JVM tìm/tạo biểu diễn runtime của một lớp hoặc interface từ định nghĩa nhị phân, thường thông qua `ClassLoader`.
- **Liên kết (linking):** kiểm tra định nghĩa, chuẩn bị các trường tĩnh và xử lý tham chiếu ký hiệu theo quy tắc JVM.
- **Khởi tạo (initialization):** thực thi khởi tạo tĩnh của lớp/interface (`<clinit>`, nếu có). **Nạp kiểu cha không có nghĩa là ngay lúc đó phải chạy static initializer của kiểu cha.**
- **Phân giải tham chiếu (resolution):** chuyển các tham chiếu ký hiệu trong constant pool thành tham chiếu runtime. Không phải mọi lớp được nhắc trong phương thức, field hoặc generic đều bắt buộc được nạp ngay cùng lúc với lớp con.

Trọng tâm của bài là những phụ thuộc trực tiếp từ **cấu trúc kế thừa**: superclass và superinterface.

## 2. Metadata nào cho JVM biết cần nạp ai?

File `.class` chứa thông tin cấu trúc, trong đó có:

| Thành phần class file | Ý nghĩa đối với quan hệ cha |
| --- | --- |
| `this_class` | Định danh nhị phân của kiểu đang được định nghĩa |
| `super_class` | Tham chiếu tới lớp cha trực tiếp của một lớp thông thường; với `java.lang.Object`, chỉ số là 0 |
| `interfaces[]` | Danh sách interface cha trực tiếp mà class/interface khai báo |
| `access_flags` | Cho biết định nghĩa là class/interface, có `final`, `abstract`, ... để kiểm tra tính hợp lệ |

Một lớp Java thông thường (ngoại trừ `java.lang.Object`) có một superclass; không ghi `extends` trong mã nguồn thì superclass là `java.lang.Object`. Một lớp có thể `implements` nhiều interface. Một interface có thể `extends` nhiều interface.

**Chi tiết đặc biệt về class file:** ở định dạng class file, `super_class` của một interface ghi `java/lang/Object`, nhưng điều đó không biến `Object` thành một “superinterface” được liệt kê trong `interfaces[]` và không thay đổi quy tắc kế thừa interface trong Java. Khi nói “superinterface trực tiếp”, ta chỉ các mục trong `interfaces[]`.

Định nghĩa một kiểu chứa nhiều tham chiếu khác ngoài quan hệ cha: kiểu tham số, kiểu trả về, field, local variable, annotation, thân phương thức. Các tham chiếu đó có thể cần resolution ở những thời điểm khác. Không được kết luận JVM **luôn nạp tất cả** các kiểu xuất hiện trong bytecode ngay khi nạp lớp.

## 3. Trình tự nạp superclass và superinterface

Theo mô hình tạo lớp/interface của JVM (JVMS §5.3), khi một định nghĩa từ bytecode được tạo ra, JVM phải thiết lập quan hệ trực tiếp trước khi hoàn tất định nghĩa mới. Có thể hình dung trình tự logic như sau:

1. Một loader nhận yêu cầu nạp tên nhị phân, ví dụ `com.example.Customer`.
2. Loader kiểm tra lớp đã được định nghĩa/chấp nhận trước đó hoặc tìm bytecode. Với parent delegation, nó có thể nhờ loader cha trước.
3. Khi JVM tạo định nghĩa `Customer`, nó sử dụng metadata để xác định `Entity` là superclass trực tiếp và `Identified` là superinterface trực tiếp.
4. JVM yêu cầu nạp các kiểu cha cần thiết thông qua quy tắc loader liên quan; thao tác này tiếp tục đệ quy cho các superclass và superinterface của chính những kiểu cha đó.
5. JVM kiểm tra quan hệ: superclass không thể là interface hay lớp `final`; superinterface được chỉ ra phải thật sự là interface; quan hệ kế thừa không được tạo vòng lặp.
6. Khi các điều kiện tương ứng thỏa mãn, JVM mới có thể hoàn tất việc tạo biểu diễn runtime của kiểu con. Linking và initialization vẫn có quy tắc/thời điểm riêng.

Ví dụ đồ thị:

```text
Customer (class)
├── extends Entity (class)
│   └── extends java.lang.Object
└── implements Identified (interface)
    └── extends Auditable (interface)
```

Các nút ở nhánh kế thừa trực tiếp và gián tiếp là phụ thuộc cần xử lý. Sơ đồ này **không phải cam kết về thứ tự log tuyệt đối** trong mọi JVM: class loading có thể diễn ra sớm do verifier, reflection, mã khác hoặc quá trình linking, và delegation có thể chuyển việc định nghĩa sang loader khác. Điều bắt buộc là những kiểu cha liên quan phải hợp lệ khi định nghĩa kiểu con thành công.

### 3.1. Superclass phải là lớp phù hợp

Với `class Customer extends Entity`, JVM cần tạo/lấy kiểu runtime tương ứng với `Entity`. `Entity` lại có superclass, thường kết thúc tại `java.lang.Object`. Nếu `Entity` không tìm thấy hoặc không thể định nghĩa, quá trình nạp `Customer` cũng có thể thất bại.

Lớp Java không thể kéo dài một lớp `final`. Trình biên dịch thường chặn trực tiếp, nhưng JVM vẫn phải bảo vệ tính hợp lệ khi gặp bytecode không hợp lệ hoặc nhị phân không tương thích, có thể báo `IncompatibleClassChangeError`.

### 3.2. Superinterface cũng là phụ thuộc của định nghĩa

Với `class Customer implements Identified`, `Identified` phải được nạp như một **interface**. Nếu `Identified extends Auditable`, việc nạp interface đó phải xử lý `Auditable`. Nếu một tên được liệt kê như superinterface lại phân giải ra class thường, JVM từ chối cấu trúc không hợp lệ, không “tự sửa” quan hệ.

Một interface có thể `extends` nhiều interface, và một class có thể `implements` nhiều interface. Vì vậy đồ thị là cấu trúc có nhánh, không phải chỉ một danh sách superclass tuyến tính.

### 3.3. Không có chuyện “khởi tạo tất cả cha” trong giai đoạn loading

Loading thiết lập định nghĩa kiểu, còn initialization chạy mã tĩnh. Vì vậy, nhìn thấy JVM đã nạp một superinterface không có nghĩa đã in ra nội dung static initializer của nó.

Phân biệt **lớp cha đã được nạp** với **lớp cha đã được khởi tạo** là kỹ năng quan trọng khi đọc log và xử lý lỗi.

## 4. Thí nghiệm Java 17+: loading khác initialization

Chương trình dưới đây cho thấy JVM có thể lấy `Class` của lớp con mà chưa chạy khởi tạo tĩnh; khi kích hoạt khởi tạo lớp con, superclass và **những superinterface khai báo default method** có quy tắc khởi tạo riêng. Interface chỉ khai báo hằng runtime mà không có default method chưa cần khởi tạo chỉ vì lớp con `implements` nó.

Lưu toàn bộ vào `ParentLoadDemo.java`:

```java
public class ParentLoadDemo {

    interface Marker {
        // Không phải compile-time constant: có lời gọi phương thức.
        int VALUE = mark("Marker");

        static int mark(String name) {
            System.out.println(name + " initialized");
            return 1;
        }
    }

    interface Behavior {
        int VALUE = mark("Behavior");

        static int mark(String name) {
            System.out.println(name + " initialized");
            return 2;
        }

        // Interface có default method.
        default String label() {
            return "demo";
        }
    }

    static class Parent {
        static {
            System.out.println("Parent initialized");
        }
    }

    static class Child extends Parent implements Marker, Behavior {
        static {
            System.out.println("Child initialized");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("1. Before load");

        Class<?> type = Class.forName(
                "ParentLoadDemo$Child",
                false,
                ParentLoadDemo.class.getClassLoader());

        System.out.println("2. Loaded: " + type.getSimpleName());
        System.out.println("3. Trigger Child initialization");

        Object instance = type.getDeclaredConstructor().newInstance();

        System.out.println("4. Child instance: " + (instance instanceof Child));
        System.out.println("5. Marker value: " + Marker.VALUE);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ParentLoadDemo.java
java ParentLoadDemo
```

**Stdout mong đợi:**

```text
1. Before load
2. Loaded: Child
3. Trigger Child initialization
Parent initialized
Behavior initialized
Child initialized
4. Child instance: true
Marker initialized
5. Marker value: 1
```

Đọc kết quả:

- `Class.forName(name, false, loader)` lấy định nghĩa `Child` nhưng không yêu cầu khởi tạo `Child`. Việc lấy tên bằng `getSimpleName()` cũng không kích hoạt `<clinit>` của `Child`.
- Lệnh tạo instance bằng reflection là **active use** của `Child`; JVM phải khởi tạo kiểu này trước khi tạo đối tượng.
- Trước khởi tạo `Child`, JVM khởi tạo superclass `Parent` và những superinterface liên quan **khai báo default method** theo quy tắc JLS/JVMS; ở đây `Behavior` được khởi tạo.
- `Marker` không khai báo default method, nên không phải khởi tạo chỉ vì `Child implements Marker`.
- Khi biểu thức `Marker.VALUE` thực sự được đọc, `VALUE` là giá trị `static final` được tính bằng gọi phương thức (không phải constant expression), làm `Marker` khởi tạo ở bước cuối.
- `(instance instanceof Child)` chỉ kiểm tra kiểu object; nó không phải lý do gây ra các dòng khởi tạo trước đó.

**Lưu ý:** ví dụ này quan sát **thời điểm initialization**, không đo toàn bộ thời điểm loading. Việc không thấy dòng `Marker initialized` ở bước 2 không chứng minh `Marker` chưa được *loaded*; chỉ chứng minh mã khởi tạo tĩnh của nó chưa chạy.

## 5. Quy tắc khởi tạo theo quan hệ cha: class và interface khác nhau

Khi **khởi tạo một class** `C`, JVM khởi tạo các superclass còn chưa khởi tạo và các superinterface liên quan **có khai báo default method** theo quy tắc về thứ tự của JLS §12.4.2/JVMS §5.5, trước khi chạy mã khởi tạo của `C`. Các interface chỉ được kế thừa gián tiếp cũng có thể liên quan qua quy tắc đệ quy ấy. Cần phân biệt **khai báo default method** với việc chỉ kế thừa một default method từ interface cha; thứ tự cụ thể phải theo định nghĩa của đặc tả, không suy ra bằng thứ tự các file JAR.

Khi **khởi tạo một interface**, JVM không bắt buộc tự động khởi tạo tất cả superinterface của nó như cách khởi tạo superclass của class. Khởi tạo interface thường xảy ra khi có active use riêng của interface hoặc các điều kiện khác theo đặc tả.

| Hành động | Superclass/superinterface cần nạp? | Khởi tạo tĩnh ngay? |
| --- | --- | --- |
| Định nghĩa `Child extends Parent implements Marker` | Phải xử lý các phụ thuộc cha tương ứng để định nghĩa `Child` | Không đồng nghĩa với việc chạy `<clinit>` |
| `Class.forName("Child", false, loader)` | Yêu cầu tìm/nạp/liên kết `Child` cùng các phụ thuộc cấu trúc cần thiết | Không chủ động khởi tạo `Child` |
| `new Child()` (sử dụng lần đầu) | Các kiểu liên quan phải sẵn sàng | Khởi tạo `Parent`, các interface có default method theo quy tắc, rồi `Child` |
| Đọc `Marker.VALUE` không phải constant expression | `Marker` phải có định nghĩa hợp lệ | Khởi tạo `Marker` nếu chưa khởi tạo |
| Đọc `SomeInterface.CONST = 10` | Có thể được compiler inline như compile-time constant | Không đủ để kết luận interface sẽ được khởi tạo |

Không nên dùng `System.out.println` trong static initializer làm bằng chứng về **loading order**, vì nó cho thấy **initialization order**. Muốn quan sát loading, dùng log chuyên dụng hoặc công cụ chẩn đoán JVM.

## 6. ClassLoader nào nạp kiểu cha?

Một class được định nghĩa bởi loader `L`, nhưng superclass hoặc superinterface của nó **không nhất thiết có cùng defining loader**. Khi JVM phân giải phụ thuộc cấu trúc theo định nghĩa của `C`, nó dùng loader phù hợp với quy tắc phân giải của `C`, rồi loader đó có thể ủy quyền cho cha.

Ví dụ hệ thống plugin:

```text
ApplicationLoader
├── api.Plugin       (interface chia sẻ)
└── api.Result       (kiểu kết quả chia sẻ)
      ↑
      ├── PluginLoaderA ── impl.PluginA implements api.Plugin
      └── PluginLoaderB ── impl.PluginB implements api.Plugin
```

Nếu `impl.PluginA` được định nghĩa bởi `PluginLoaderA` và `api.Plugin` được định nghĩa bởi `ApplicationLoader`, thì quan hệ `implements` vẫn hợp lệ: loader của lớp con có thể yêu cầu kiểu cha và nhận `Class` do cha định nghĩa.

Nhưng nếu loader của plugin tự định nghĩa một bản `api.Plugin` khác với bản của host, hai interface có thể cùng tên nhưng **khác danh tính kiểu**. Khi host ép đối tượng `impl.PluginA` sang `api.Plugin` của host, cast có thể thất bại dù plugin “đã implements Plugin”.

Danh tính runtime của một kiểu được xác định bởi **(binary name, defining loader)**. Sự khác nhau giữa **initiating loader** (yêu cầu load) và **defining loader** (thực sự định nghĩa lớp) giải thích tại sao hai plugin khác nhau vẫn có thể chia sẻ một interface cha duy nhất.

### 6.1. Parent delegation không có nghĩa cha tự nhìn thấy lớp con

Loader con thường hỏi loader cha trước theo cơ chế parent-first, nhưng loader cha không tự tìm xuống mọi loader con. Khi host định nghĩa `api.Plugin`, plugin loader có thể dùng chung interface ấy; ngược lại, host không tự động nạp được mọi `impl.PluginA`.

Một class loader tùy biến có thể thiết kế child-first hoặc delegation chọn lọc. Dù chọn cách nào, các **API/SPI dùng chung** ở ranh giới host–plugin thường cần cùng một defining loader để giữ tương thích kiểu.

### 6.2. JVM kiểm tra ràng buộc loader khi liên kết kiểu

Không chỉ đơn giản so sánh tên và thử cast: JVM còn áp dụng **loading constraints** trong những tình huống liên kết cần bảo đảm tính nhất quán kiểu giữa các loader. Nếu cùng một tên xuất hiện trong chữ ký phương thức xuyên qua các kiểu đã được liên kết mà định nghĩa runtime mâu thuẫn, JVM có thể báo `LinkageError` (ví dụ `loader constraint violation`).

Không nên cố chữa lỗi bằng cách ép hai plugin cùng classpath một cách tùy tiện; cần xác định **kiểu nào phải dùng chung** và **kiểu nào thật sự được cô lập**.

## 7. Nếu không nạp được kiểu cha thì điều gì xảy ra?

Một điểm dễ bỏ sót là ứng dụng có thể tải được bytecode của `Child.class` nhưng vẫn **không thể định nghĩa `Child` hợp lệ** vì thiếu hoặc sai `Parent.class` hay interface cha.

### Tình huống 1: thiếu superclass ở runtime

```java
// Parent.java
public class Parent {}
```

```java
// Child.java
public class Child extends Parent {}
```

Hai file compile thành công nếu cùng classpath. Nhưng giả sử khi triển khai chỉ có `Child.class` mà `Parent.class` không còn trong đường dẫn mà class loader sử dụng: lần đầu nạp `Child` có thể báo `NoClassDefFoundError: Parent` (thường có `ClassNotFoundException` ở phần cause bên dưới).

Điểm cần kiểm tra: **thông báo nêu Parent** không nhất thiết có nghĩa lệnh trực tiếp của bạn yêu cầu nạp `Parent`; nó có thể là phụ thuộc kế thừa bắt buộc của `Child`.

### Tình huống 2: thiếu một superinterface

```java
// Auditable.java
public interface Auditable {}
```

```java
// Child.java
public class Child implements Auditable {}
```

Khi runtime không thể tìm `Auditable`, `Child` cũng không thể được tạo định nghĩa kiểu thành công theo quan hệ `implements`. Vấn đề phát sinh ngay cả khi ứng dụng **chưa gọi một phương thức nào** của `Auditable`.

### Tình huống 3: bytecode không hợp lệ hoặc đổi phiên bản không tương thích

Một số lỗi điển hình:

| Dấu hiệu | Cần nghĩ đến điều gì |
| --- | --- |
| `NoClassDefFoundError: Parent` | Superclass/superinterface hoặc phụ thuộc bắt buộc không khả dụng lúc JVM cần; cũng có thể liên quan đến initialization thất bại trước đó, cần đọc cause |
| `ClassNotFoundException` | API nạp bằng tên không tìm thấy yêu cầu; khác với `NoClassDefFoundError` do việc liên kết/định nghĩa phụ thuộc |
| `IncompatibleClassChangeError` | Bytecode mong đợi class nhưng runtime lại là interface, hoặc ngược lại; kế thừa class `final` không hợp lệ cũng thuộc nhóm lỗi này |
| `ClassCircularityError` | Quan hệ superclass/superinterface hình thành vòng tròn không hợp lệ khi loading |
| `VerifyError` | JVM verifier phát hiện bytecode không đáp ứng yêu cầu an toàn kiểu hoặc ràng buộc liên quan |
| `LinkageError` có `loader constraint violation` | Hai loader định nghĩa các kiểu không tương thích trong một quan hệ cần nhất quán |
| `ExceptionInInitializerError` | Đã bước sang **initialization**, một initializer tĩnh thất bại; không phải bằng chứng chắc chắn loading superclass thất bại |

**Cảnh báo phân loại:** `ClassNotFoundException` là checked exception có thể xuất hiện khi gọi `Class.forName` cho **tên được yêu cầu**; `NoClassDefFoundError` là một `LinkageError` thường cho thấy JVM không thể dùng một định nghĩa phụ thuộc đã được mong đợi. Hai loại này không được xử lý bằng cách chỉ catch một loại và đoán lớp nào hỏng.

### Ví dụ kiểm tra dependency tại runtime

Không cần viết lại class loader để quan sát tình huống thiếu superclass. Trên một môi trường thử nghiệm:

1. Biên dịch cả `Parent.java` và `Child.java`: `javac Parent.java Child.java`.
2. Di chuyển `Parent.class` ra khỏi **classpath của tiến trình thử nghiệm**, không đụng bản triển khai thật.
3. Yêu cầu tải `Child` qua `Class.forName("Child", false, loader)`.
4. Quan sát chuỗi `Throwable`, đặc biệt tên lớp bị thiếu và nguyên nhân lồng trong `Caused by`.
5. Khôi phục đúng file/lớp phụ thuộc trước khi kiểm tra tiếp.

Thao tác trên chỉ là kịch bản thử nghiệm được mô tả, không có stdout cố định áp dụng cho mọi cấu hình loader/JVM.

## 8. Thứ tự loading, linking, initialization và resolution: đừng trộn lẫn

Xét quan hệ:

```java
interface Audit {}
class Root {}
class Order extends Root implements Audit {
    static Helper helper;
}
class Helper {}
```

Các phân biệt cần giữ rõ:

1. Để tạo định nghĩa runtime của `Order`, JVM phải xử lý `Root` và `Audit` như những **kiểu cha trực tiếp**.
2. Việc `Order` có field `Helper helper` không cho phép suy luận `Helper` **bắt buộc phải được khởi tạo** cùng `Order`. Việc resolution của tham chiếu `Helper` có thể xảy ra theo thời điểm khác, tùy nhu cầu và JVM.
3. `Root` có thể đã được nạp trước đó bởi code khác; khi nạp `Order`, JVM tái sử dụng định nghĩa sẵn có từ loader phù hợp thay vì định nghĩa trùng một kiểu.
4. Nếu `Order` được khởi tạo, superclass `Root` phải được khởi tạo trước; `Audit` **không nhất thiết** được khởi tạo nếu không thỏa điều kiện khởi tạo interface.
5. Quá trình **verify** và **resolve** có thể yêu cầu JVM xử lý thêm kiểu ngoài các kiểu cha trực tiếp. Vì vậy, “superclass và superinterface là bắt buộc” không có nghĩa “chỉ chúng mới có thể được nạp lúc đó”.

### Hình dung theo hai trục

```text
Phụ thuộc cấu trúc:
Order ──extends──> Root ──extends──> Object
   └──implements──> Audit

Các giai đoạn đời sống của từng kiểu:
Loading ──> Linking [verify → prepare → resolve khi thích hợp] ──> Initialization
             (resolution có thể được thực hiện sớm hoặc muộn)
```

Quan hệ cấu trúc cho biết **cần có kiểu nào để định nghĩa lớp**; các giai đoạn đời sống cho biết **JVM làm những việc gì đối với từng kiểu**. Hai trục phải được phân tích riêng.

## 9. Cách chẩn đoán khi thiếu lớp cha hoặc interface cha

Khi gặp lỗi class loading ở một ứng dụng lớn, đi theo trình tự sau thay vì chỉ thêm JAR ngẫu nhiên:

1. **Xác định lớp đang được yêu cầu nạp.** Ghi binary name trong `Class.forName`, `ClassLoader.loadClass`, stack trace hoặc điểm tạo đối tượng.
2. **Đọc toàn bộ exception chain.** Phân biệt tên `Child` được yêu cầu với tên `Parent`/interface bị thiếu trong cause.
3. **Xác định định nghĩa `extends` và `implements`.** Có thể dùng `javap -p -verbose Child.class` để xem `super_class` và `interfaces` ở bytecode, kể cả khi code nguồn không còn.
4. **Kiểm tra classpath/module path thực sự của tiến trình.** Một file JAR tồn tại trên đĩa không chứng minh loader hiện tại có quyền truy cập tới nó.
5. **Kiểm tra loader và delegation.** In `clazz.getClassLoader()` với những lớp đã nạp được, xác định parent loader và tập URL/JAR của plugin loader tùy biến.
6. **Theo dõi log loading.** Với HotSpot/JDK 17+, có thể chạy `java -Xlog:class+load=info ...` để biết nhiều lớp được lấy từ nguồn nào. Log nạp lớp và dòng `<clinit>` không có cùng ý nghĩa.
7. **Nếu lỗi liên quan module**, kiểm tra readability, exports/opens theo tình huống. Đây là ràng buộc bổ sung; không làm mất các yêu cầu nạp kiểu cha.
8. **Nếu có version conflict**, đối chiếu JAR đã compile với JAR runtime; đặc biệt lưu ý việc class đổi từ interface sang class, đổi superclass hoặc đổi quan hệ implements.
9. **Kiểm tra trường hợp hot reload/plugin reload.** Một loader mới có thể định nghĩa `Child` mới, trong khi host còn giữ interface hoặc instance từ loader cũ; cần xem danh tính kiểu runtime và tham chiếu giữ loader cũ.

Với kiểu đã nạp được, đoạn hỗ trợ sau cung cấp manh mối:

```java
static void inspect(Class<?> type) {
    System.out.println("Type: " + type.getName());
    System.out.println("Loader: " + type.getClassLoader());
    Class<?> parent = type.getSuperclass();
    System.out.println("Superclass: " +
            (parent == null ? "<none>" : parent.getName()));
    for (Class<?> iface : type.getInterfaces()) {
        System.out.println("Direct interface: " + iface.getName());
    }
}
```

Đây là **phương thức hỗ trợ**, đưa vào một class đang chạy rồi gọi `inspect(SomeType.class)`. `getInterfaces()` trả về các interface **trực tiếp**; muốn xem transitive closure cần duyệt thêm interface cha của từng interface. `getSuperclass()` trả về `null` cho `Object`, interface và một số kiểu đặc biệt như primitive/array theo API; đó không phải bằng chứng tải class thất bại.

## 10. Những nhầm lẫn thường gặp

- **“File `Child.class` tồn tại là đủ để nạp được `Child`.”** Sai nếu superclass/superinterface trực tiếp hoặc gián tiếp không tải được.
- **“JVM chỉ nạp superclass, không cần superinterface.”** Sai: interface cha trực tiếp và chuỗi interface cha của chúng cũng là quan hệ cấu trúc cần xử lý.
- **“Superinterface nạp đồng nghĩa static field của nó đã khởi tạo.”** Sai: loading và initialization khác nhau; quy tắc default method chỉ chi phối một số tình huống khởi tạo class.
- **“Đối tượng chưa được tạo nghĩa là chưa load cha.”** Sai: JVM có thể load/link lớp trước active use, nhất là qua reflection hoặc verifier.
- **“Cứ interface có default method là lúc load `Child` nó lập tức chạy initializer.”** Sai: kích hoạt khởi tạo class mới liên quan đến quy tắc khởi tạo superclass/superinterface; loading riêng không kích hoạt.
- **“Cùng tên interface là đủ cho `implements` xuyên plugin.”** Sai: cần cùng danh tính kiểu ở runtime, bao gồm defining loader.
- **“Thiếu superclass phải ra `ClassNotFoundException`.”** Thường có thể xuất hiện `NoClassDefFoundError` cho phụ thuộc; phải xem toàn bộ cause.
- **“Mọi kiểu xuất hiện trong khai báo field/method đều bắt buộc load ngay cùng lớp con.”** Sai: phụ thuộc cấu trúc kế thừa và resolution tham chiếu khác có cơ chế, thời điểm riêng.

## 11. Câu hỏi tự kiểm tra

**1. `class Invoice extends Document implements Serializable`: khi nạp `Invoice`, kiểu nào là phụ thuộc cấu trúc?**

`Document` (và chuỗi superclass cần thiết), `Serializable` (cùng các superinterface liên quan, nếu có). `java.lang.Object` xuất hiện ở đỉnh chuỗi class trừ bản thân `Object`.

**2. `Class.forName("Invoice", false, loader)` thành công có bảo đảm `static { ... }` trong `Document` đã chạy?**

Không. Nạp và liên kết khác với khởi tạo. Tham số `false` yêu cầu không chủ động khởi tạo lớp được chọn; nếu một kiểu đã được khởi tạo do hành động trước đó, API không hoàn tác trạng thái ấy.

**3. Nếu `Invoice implements A, B`, `B extends C` và `C` biến mất khỏi runtime?**

Không thể coi `B` là interface hoàn chỉnh khi thiếu superinterface bắt buộc của nó, vì vậy việc nạp `Invoice` có thể thất bại khi giải quyết chuỗi phụ thuộc cấu trúc.

**4. Interface `Feature` đã được load, nhưng initializer của `Feature` chưa chạy. Có mâu thuẫn không?**

Không. Interface có thể được load trước khi được initialize. Việc khởi tạo một class implements `Feature` không nhất thiết khởi tạo `Feature` nếu `Feature` không khai báo default method và chưa được dùng theo cách khác kích hoạt initialization.

**5. Hai plugin đều `implements api.Plugin`, vì sao có plugin không cast được sang `api.Plugin` của host?**

Vì `api.Plugin` trong một plugin có thể do loader khác tự định nghĩa, tạo kiểu runtime riêng. Host và plugin cần thống nhất interface API/SPI do loader chia sẻ định nghĩa.

## 12. Kết luận và tài liệu đối chiếu

Để định nghĩa một class/interface hợp lệ, JVM phải xử lý những **superclass và superinterface mà metadata khai báo** cùng các phụ thuộc kế thừa đệ quy, kiểm tra tính hợp lệ của quan hệ đó trong môi trường class loader. Việc này thuộc **loading/creation** và liên hệ với **linking**; nó không tương đương việc chạy **initialization** của mọi kiểu cha.

Khi gặp lỗi nạp lớp con, hãy bắt đầu từ ba câu hỏi: **kiểu cha nào là bắt buộc, loader nào đang tìm/định nghĩa kiểu đó, và lỗi xảy ra trong loading, linking hay initialization?**

Tài liệu chuẩn để đọc sâu:

- *Java Virtual Machine Specification*, §5.3 “Creation of Classes and Interfaces”: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- *Java Virtual Machine Specification*, §5.4 “Linking”: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4
- *Java Virtual Machine Specification*, §5.5 “Initialization”: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- *Java Language Specification*, §12.4 “Initialization of Classes and Interfaces”: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4
