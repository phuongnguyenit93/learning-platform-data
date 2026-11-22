# Khả năng dỡ lớp ẩn độc lập với class loader (Java 15+)

## 1. Tại sao hidden class có vòng đời khác lớp Java thông thường?

Từ **Java 15**, API `MethodHandles.Lookup.defineHiddenClass` cho phép JVM tạo một **hidden class** (lớp ẩn) từ bytecode. Hidden class phục vụ các công cụ sinh mã tại thời gian chạy, chẳng hạn những framework cần tạo nhiều lớp phụ trợ có vòng đời ngắn. Một đặc tính quan trọng của nó là **khả năng dỡ lớp (class unloading) có thể độc lập với việc class loader còn tồn tại**.

Đối với lớp Java thông thường, vòng đời của lớp gắn chặt với **defining class loader**: theo quy tắc class unloading, một lớp bình thường chỉ có thể bị dỡ khi class loader định nghĩa nó có thể được garbage collector thu hồi. Nếu loader vẫn cần tồn tại để phục vụ nhiều lớp khác, các lớp bình thường của loader thường cũng được giữ.

**Hidden class mặc định khác ở điểm này:** một lớp ẩn được định nghĩa **không kèm `ClassOption.STRONG`** có thể được dỡ **ngay cả khi class loader được đánh dấu là defining loader của nó vẫn còn reachable**. Đây là khả năng, **không phải lời hứa rằng JVM sẽ dỡ lớp ngay hoặc chắc chắn trong mọi lần chạy**.

Ngược lại, `MethodHandles.Lookup.ClassOption.STRONG` đưa lớp ẩn trở lại **quan hệ mạnh với defining loader giống lớp thông thường**: nó chỉ có thể được dỡ khi chính defining loader đủ điều kiện được thu hồi.

Như vậy, lựa chọn vòng đời nằm ngay trong lời gọi tạo hidden class:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

// Mac dinh: hidden class co kha nang unload doc lap voi loader.
MethodHandles.Lookup weakHidden =
        lookup.defineHiddenClass(classBytes, false);

// STRONG: unloading gan voi vong doi defining loader.
MethodHandles.Lookup strongHidden =
        lookup.defineHiddenClass(
                classBytes,
                false,
                MethodHandles.Lookup.ClassOption.STRONG);
```

Đây là mã **minh họa** trong ngữ cảnh đã có `classBytes` hợp lệ. Tham số thứ hai `false` là `initialize` (không yêu cầu chạy class initializer ngay), **không phải công tắc bật/tắt unloading**. Khả năng unloading được quyết định bởi sự hiện diện của `ClassOption.STRONG`.

## 2. Cần phân biệt ba khái niệm

### 2.1. Định nghĩa lớp (definition)

Khi `defineHiddenClass` nhận class file hợp lệ, JVM tạo **danh tính lớp ẩn mới**, liên kết nó với runtime package, protection domain và class loader theo quy định của `Lookup`.

Mỗi lần `defineHiddenClass` tạo ra một danh tính lớp mới, kể cả khi hai lần dùng **cùng mảng bytecode**. Vì vậy hai hidden class có thể:

- Cùng hình dạng bytecode và cùng các tên phương thức.
- Cùng một defining loader.
- Nhưng có hai đối tượng `Class<?>` mang **hai danh tính lớp khác nhau**.
- Có trạng thái khởi tạo, trường `static` và khả năng dỡ lớp riêng.

Điều đó cho phép một runtime tạo các lớp phụ trợ tạm thời rồi không giữ chúng lâu hơn cần thiết.

### 2.2. Khởi tạo lớp (initialization)

Khởi tạo là thời điểm JVM thực thi mã `<clinit>` tạo từ các biểu thức gán trường `static` và khối `static { ... }`.

Trong API:

```java
lookup.defineHiddenClass(bytes, true);  // Yeu cau khoi tao ngay
lookup.defineHiddenClass(bytes, false); // Chua yeu cau khoi tao ngay
```

`true` / `false` chỉ quyết định **thời điểm khởi tạo trong lời gọi này**. Chúng **không tự quyết định** lớp có được dỡ trước loader hay không.

Một hidden class có thể được khởi tạo thành công rồi sau đó vẫn được dỡ nếu trở nên không còn được sử dụng và thỏa các điều kiện JVM. **Khởi tạo một lần không có nghĩa giữ class mãi trong bộ nhớ**.

### 2.3. Dỡ lớp (class unloading)

Class unloading là việc JVM giải phóng metadata và tài nguyên runtime liên quan đến một class khi việc dỡ được cho phép và JVM thực hiện thu gom thích hợp.

- **Lớp bình thường / hidden class `STRONG`:** gắn vòng đời unloading với defining loader.
- **Hidden class mặc định (không `STRONG`):** *có thể* được dỡ khi class trở nên không còn được giữ sống, **dù loader của nó vẫn còn reachable**.
- **Cả hai loại:** chương trình không thể dựa vào một thời điểm dỡ lớp chính xác; class unloading là phần tối ưu hóa do JVM/garbage collector quyết định.

Class unloading **không phải** gọi `close()` hoặc `dispose()` lên đối tượng `Class<?>`. API `Class` không cung cấp phương thức chuẩn yêu cầu “unload class này ngay”.

## 3. Class loader vẫn là defining loader của cả hai loại hidden class

Tên “dỡ lớp độc lập với class loader” dễ khiến người học tưởng hidden class **không có class loader**. Điều đó sai.

Khi dùng `defineHiddenClass`, hidden class vẫn được đánh dấu có **defining loader**, thường là class loader liên quan đến lookup class. Bạn có thể xem qua `hiddenClass.getClassLoader()`.

Điểm khác nhau là **mối liên hệ giữ class sống** (*liveness relationship*):

| Loại class | Có defining loader? | Có thể unload khi loader vẫn reachable? | Ý nghĩa |
| --- | --- | --- | --- |
| Class thông thường | Có | **Không**, theo quy tắc class unloading thông thường | Vòng đời gắn với loader. |
| Hidden class mặc định, không `STRONG` | Có | **Có thể** | JVM có quyền thu hồi riêng khi class không còn được giữ sống. |
| Hidden class có `STRONG` | Có | **Không**, theo quan hệ mạnh được chỉ định | Unloading gắn với vòng đời loader như class thường. |

**“Có thể” là từ khóa quan trọng.** JVM không bắt buộc thu hồi ngay khi mọi tham chiếu ứng dụng biến mất. Nó có thể trì hoãn class unloading, chưa chạy GC hoặc chọn không dỡ một class nào ở thời điểm bạn quan sát.

**`STRONG` cũng không có nghĩa “vĩnh viễn”:** nếu defining loader về sau không còn reachable và GC chọn thu hồi nó, các class gắn với loader có thể được dỡ. Nhưng `STRONG` sẽ khiến hidden class **không có ưu điểm dỡ riêng khi loader vẫn sống**.

## 4. Ví dụ Java chạy được: cùng loader, hai chính sách vòng đời

Ví dụ cố ý **không phụ thuộc vào thời điểm garbage collection**. Nó chứng minh điều có thể kiểm tra chắc chắn: cả hai hidden class đều được tạo qua cùng `Lookup`, đều là hidden class, cùng loader, nhưng có danh tính lớp khác nhau. Khác biệt về chính sách dỡ lớp được xác định bằng `ClassOption.STRONG` theo Java API.

Tạo **hai file Java trong cùng thư mục**, cùng package (ở đây dùng package mặc định).

### File `HiddenPayload.java`

```java
class HiddenPayload {
    static String message() {
        return "READY";
    }
}
```

### File `HiddenLifetimeDemo.java`

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;

public class HiddenLifetimeDemo {
    public static void main(String[] args) throws Throwable {
        byte[] bytes = Files.readAllBytes(
                Path.of("HiddenPayload.class")
        );
        MethodHandles.Lookup host = MethodHandles.lookup();

        MethodHandles.Lookup defaultLookup =
                host.defineHiddenClass(bytes, false);
        MethodHandles.Lookup strongLookup =
                host.defineHiddenClass(
                        bytes,
                        false,
                        MethodHandles.Lookup.ClassOption.STRONG
                );

        Class<?> normalLifetime = strongLookup.lookupClass();
        Class<?> independentlyUnloadable =
                defaultLookup.lookupClass();
        ClassLoader appLoader =
                HiddenLifetimeDemo.class.getClassLoader();

        System.out.println(
                "weakHidden=" + independentlyUnloadable.isHidden()
        );
        System.out.println(
                "strongHidden=" + normalLifetime.isHidden()
        );
        System.out.println(
                "sameDefiningLoader=" +
                (independentlyUnloadable.getClassLoader() == appLoader
                        && normalLifetime.getClassLoader() == appLoader)
        );
        System.out.println(
                "differentClassObjects=" +
                (independentlyUnloadable != normalLifetime)
        );

        MethodHandle call = defaultLookup.findStatic(
                independentlyUnloadable,
                "message",
                MethodType.methodType(String.class)
        );
        System.out.println("invoke=" + (String) call.invokeExact());
    }
}
```

Biên dịch **cả hai file** với JDK 17+; tùy chọn `--release 15` giữ cú pháp/API trong phạm vi Java 15:

```bash
javac --release 15 -encoding UTF-8 HiddenPayload.java HiddenLifetimeDemo.java
java HiddenLifetimeDemo
```

Chạy lệnh tại thư mục chứa hai file, để `Path.of("HiddenPayload.class")` tìm được class file vừa sinh ra.

**Đầu ra đã biên dịch và chạy thành công với JDK 24, `--release 15`:**

```text
weakHidden=true
strongHidden=true
sameDefiningLoader=true
differentClassObjects=true
invoke=READY
```

Giải thích:

1. `weakHidden=true`: hidden class mặc định thật sự được tạo; `Class.isHidden()` trả `true`.
2. `strongHidden=true`: thêm `STRONG` không biến nó thành normal class. Nó **vẫn là hidden class**.
3. `sameDefiningLoader=true`: hai hidden class đều gắn với cùng loader của lớp gọi.
4. `differentClassObjects=true`: hai lần định nghĩa tạo hai danh tính class riêng, dù cùng bytecode.
5. `invoke=READY`: runtime có thể gọi một phương thức của hidden class thông qua `Lookup` và `MethodHandle` phù hợp.

**Ví dụ không in “class đã được unload”.** Chạy được phương thức chỉ chứng minh lớp đang được sử dụng tại thời điểm đó; nó **không** chứng minh hidden class mặc định sẽ được dỡ trước khi `main` kết thúc. Việc có thể được dỡ khi loader vẫn sống là **hợp đồng của API**, không phải một kết quả bắt buộc trong từng lần GC.

## 5. Tại sao `ClassOption.STRONG` tồn tại?

Mặc định weak cho phép giải phóng các hidden class dùng tạm, nhưng có những trường hợp class phụ trợ phải tồn tại **gần như đồng thời với một lớp chính** hoặc với toàn bộ vòng đời loader.

Ví dụ về ý tưởng thiết kế:

- Một framework sinh hàng nghìn hidden class để thực thi phép biến đổi ngắn hạn; không nên giữ toàn bộ class metadata chỉ vì một application loader sống lâu.
- Một hệ thống sinh helper class gắn chặt với tính đúng đắn hoặc vòng đời của một runtime class dài hạn; nó có thể yêu cầu quan hệ mạnh như các class thông thường.
- Một công cụ cần chọn rõ giữa **cho phép dỡ sớm** và **giữ đến khi loader có thể thu hồi**.

Java cung cấp `MethodHandles.Lookup.ClassOption.STRONG`:

```java
MethodHandles.Lookup lifetimeWithLoader =
        host.defineHiddenClass(
                bytes,
                false,
                MethodHandles.Lookup.ClassOption.STRONG
        );
```

`STRONG` nghĩa là **hidden class có quan hệ mạnh với class loader được đánh dấu là defining loader**, như class hoặc interface thông thường có với loader của nó.

Lựa chọn chính sách dỡ lớp được **ấn định khi định nghĩa class** và **không thể đổi về sau** cho chính danh tính class đó. Không có `lookup.setStrong(false)`, `Class.setUnloadable(true)` hay chức năng chuẩn nào để đổi kiểu liveness sau khi class đã được tạo.

Nếu muốn một hidden class mới có chính sách khác, có thể **định nghĩa một danh tính class mới** từ bytecode phù hợp với tùy chọn khác; điều đó không sửa chính sách class cũ và không chuyển dữ liệu `static` từ class cũ sang class mới.

### 5.1. Còn `NESTMATE` thì sao?

`ClassOption.NESTMATE` là tùy chọn về **quan hệ nest** và quyền truy cập các thành viên `private` trong cùng nest. Nó **không thay thế** `STRONG`.

Có thể kết hợp:

```java
MethodHandles.Lookup hidden = host.defineHiddenClass(
        bytes,
        false,
        MethodHandles.Lookup.ClassOption.NESTMATE,
        MethodHandles.Lookup.ClassOption.STRONG
);
```

Đoạn trên chỉ minh họa cú pháp trong ngữ cảnh đã có `host` và `bytes` phù hợp. Tùy chọn `NESTMATE` ảnh hưởng quyền truy cập; `STRONG` ảnh hưởng quan hệ unloading với loader; `initialize=false` ảnh hưởng thời điểm khởi tạo.

## 6. Những tham chiếu nào khiến hidden class mặc định vẫn sống?

**Mặc định weak không có nghĩa “sẽ unload dù chương trình đang dùng”.** Để JVM có thể thu hồi một class, class đó phải không còn các nguồn giữ sống cần thiết. Cần cân nhắc những thứ runtime đang giữ:

| Tham chiếu/tình huống | Vì sao quan trọng? |
| --- | --- |
| `Class<?> hiddenClass` còn được giữ mạnh trong biến, collection hoặc cache | Đối tượng `Class` reachable có thể khiến hidden class không được dỡ. |
| `MethodHandles.Lookup hiddenLookup` được giữ lâu | Lookup gắn với lookup class, có thể giữ lớp ẩn reachable. |
| `MethodHandle` trỏ đến phương thức/constructor/field của hidden class | Handle có thể giữ metadata, member và class liên quan; cache handle có thể kéo dài vòng đời lớp. |
| Một instance của hidden class còn sống | Instance cần class của nó để hoạt động; class không thể bị dỡ chỉ vì không còn một biến `Class<?>` riêng. |
| Stack frame đang thực thi mã của hidden class | JVM cần class đang được sử dụng cho lời gọi đang chạy. |
| Framework giữ cache, callback, class metadata hoặc tham chiếu gián tiếp | Dù biến cục bộ bị bỏ, những tham chiếu khác vẫn có thể giữ class sống. |

**Nguyên tắc thiết kế:** Nếu muốn tận dụng unloading độc lập, đừng vô tình cache vĩnh viễn `Class<?>`, `Lookup`, `MethodHandle`, instance hoặc những đối tượng khác liên quan đến class dùng tạm. Nếu có cache, thiết kế giới hạn dung lượng, phạm vi và cơ chế hết hạn phù hợp.

Việc gán `hiddenClass = null` **không đủ để chứng minh** lớp sẽ unload: có thể vẫn còn `Lookup`, handle, instance, tài nguyên của JVM hoặc các tham chiếu khác.

Ngược lại, nếu bạn **muốn giữ một hidden class mặc định**, có thể giữ `Class<?>` reachable theo tài liệu `Lookup`; không phải mọi trường hợp đều cần `STRONG`. Nhưng cần hiểu chính sách mặc định và quản lý liveness có chủ đích.

## 7. `WeakReference<Class<?>>` và GC: chỉ quan sát, không bảo đảm

`WeakReference` giúp **quan sát khả năng thu hồi** của đối tượng `Class<?>`, nhưng nó **không yêu cầu JVM chạy GC**, không bảo đảm thời điểm `get()` chuyển thành `null` và không phải phép kiểm thử xác định về class unloading.

Một đoạn minh họa cách giữ *tham chiếu yếu* thay vì giữ mạnh:

```java
import java.lang.invoke.MethodHandles;
import java.lang.ref.WeakReference;

// Dat phuong thuc nay trong class duoc phep define hidden class.
static WeakReference<Class<?>> makeWeakCandidate(byte[] bytes)
        throws IllegalAccessException {

    MethodHandles.Lookup temporaryLookup =
            MethodHandles.lookup().defineHiddenClass(bytes, false);

    Class<?> temporaryClass = temporaryLookup.lookupClass();

    // Tra ve tham chieu yeu; khong tra Lookup hay Class truc tiep.
    return new WeakReference<>(temporaryClass);
}
```

Đây là **mã minh họa phương thức**, cần đặt bên trong một class phù hợp và truyền bytecode cùng package hợp lệ. Trong ví dụ, sau khi phương thức trả về và không còn tham chiếu mạnh nào khác, class ẩn **có thể đủ điều kiện** để JVM thu hồi. Điều đó không có nghĩa một lần `System.gc()` sẽ khiến nó biến mất.

Nếu một chương trình thử quan sát:

```java
WeakReference<Class<?>> candidate = makeWeakCandidate(bytes);

System.gc(); // Chi la loi goi y, JVM khong phai thuc hien.
System.out.println(candidate.get() == null);
```

thì kết quả **có thể là `true` hoặc `false`** tùy trạng thái reachability, JVM, GC, thời điểm và chính sách class unloading. Đoạn này là **minh họa trong bối cảnh đã có `bytes`**, không có stdout cố định được cam kết.

**Không viết unit test kiểu `assertNull(candidate.get())` sau `System.gc()`.** Một test như vậy dễ thất bại ngẫu nhiên trên CI dù ứng dụng đúng. Hãy kiểm tra hành vi nghiệp vụ có tính quyết định; khi nghiên cứu class unloading, dùng công cụ quan sát JVM và đánh giá dữ liệu theo điều kiện cụ thể.

### 7.1. Quan sát GC/class unloading trên HotSpot

Với HotSpot trong OpenJDK, có thể bật unified logging:

```bash
java -Xlog:class+unload=info HiddenLifetimeDemo
```

Tùy chọn trên cho phép theo dõi các sự kiện class unloading **nếu có xảy ra**. Một lần chạy chương trình ngắn không xuất hiện log unload **không chứng minh** lớp mặc định bị giữ vĩnh viễn; có thể JVM chưa chạy pha GC/unloading thích hợp.

Trong các thử nghiệm tải thực tế, hãy:

1. Tạo nhiều hidden class trong một vòng đời được kiểm soát.
2. Bỏ mọi tham chiếu mạnh không còn cần thiết, kể cả cache `Lookup` và `MethodHandle`.
3. Giữ loader sống trong khi quan sát để đánh giá **khả năng dỡ class độc lập**.
4. Thu thập log class unload và mức dùng class metadata/metaspace bằng công cụ phù hợp với JVM đang chạy.
5. So sánh với trường hợp định nghĩa bằng `STRONG` khi cùng loader còn sống.

`-Xlog:class+unload` là tùy chọn của môi trường JVM hỗ trợ unified logging; cú pháp log và sự kiện cụ thể là công cụ chẩn đoán của implementation, **không phải API Java chuẩn bảo đảm một thứ tự unload cố định**.

## 8. Tại sao unloading độc lập hữu ích với bộ nhớ?

JVM dùng metadata để mô tả class: cấu trúc kiểu, method, field, thông tin liên kết và các tài nguyên runtime khác. Khi ứng dụng liên tục sinh nhiều lớp phụ trợ, số lượng lớp tồn tại có thể gây áp lực bộ nhớ **ngay cả khi object nghiệp vụ đã không còn được dùng**.

Ví dụ điển hình:

- Một framework tạo hidden class cho mỗi lệnh thực thi hoặc adapter động, xong công việc thì bỏ tham chiếu.
- Class loader của ứng dụng vẫn sống vì nó quản lý nhiều thành phần khác.
- Nếu mọi helper class đều buộc sống đến lúc loader biến mất, class metadata có thể tăng theo số helper từng tạo.
- Hidden class mặc định cho JVM **cơ hội** thu hồi metadata của helper không còn được dùng trong khi loader vẫn hoạt động.

Đây là lợi thế về **quản lý vòng đời**. Nó không cam kết mọi tải làm việc đều giải phóng bộ nhớ ngay, cũng không sửa được việc cache vô hạn hoặc giữ object không cần thiết.

Khi cân nhắc `STRONG`, hãy tự hỏi: “Class phụ trợ này phải tồn tại **suốt vòng đời loader**, hay chỉ **khi còn sử dụng**?” Với các lớp sinh rất nhiều và tồn tại ngắn, không dùng `STRONG` thường có lợi cho khả năng thu hồi. Với lớp gắn chặt vòng đời vào loader, `STRONG` có thể phù hợp hơn.

Không thể thay thế việc đo đạc: theo dõi lượng class đang sống, xu hướng metaspace, tốc độ tạo class, cache runtime và các lần GC/class unloading thực tế.

## 9. So sánh class unloading với object garbage collection

Đây là một nguồn nhầm lẫn lớn:

- **Object GC:** JVM có thể thu hồi **đối tượng thông thường** khi nó không còn reachable.
- **Class unloading:** JVM có thể thu hồi **định nghĩa class và metadata** khi điều kiện JVM cho phép. Một class không tự bị unload ngay chỉ vì một instance cụ thể bị GC.
- **Class loader reclamation:** JVM có thể thu hồi **class loader object** khi nó không còn được giữ sống; điều này liên quan chặt với unloading của các class thông thường và hidden class `STRONG`.
- **Default hidden class:** có thể được dỡ độc lập với thời điểm loader được thu hồi, miễn là các điều kiện liveness thực tế cho phép.

Hình dung hai cách:

```text
Normal class / hidden class STRONG:
    loader con reachable -> class chua du dieu kien unload rieng

Hidden class mac dinh:
    loader con reachable
        |
        +-- hidden class A con tham chieu -> van can ton tai
        |
        +-- hidden class B het tham chieu -> co the duoc unload rieng
```

Sơ đồ chỉ minh họa **điều kiện đủ tư cách để dỡ**, không diễn tả thuật toán GC cố định và không nói JVM phải unload class B ngay lập tức.

## 10. Giới hạn và lỗi thường gặp

| Nhận định / cách làm sai | Vì sao không đúng? | Cách hiểu chính xác |
| --- | --- | --- |
| “Hidden class không có class loader.” | Hidden class vẫn có defining loader. | Khác biệt ở **quan hệ unloading**, không phải việc không có loader. |
| “Không truyền `STRONG` thì lớp được unload ngay.” | Unloading phụ thuộc reachability và quyết định của JVM/GC. | **Có thể** dỡ độc lập nếu không còn được giữ sống. |
| “Truyền `STRONG` biến hidden class thành class bình thường.” | Nó vẫn có `Class.isHidden() == true` và đặc tính không tra theo tên thông thường. | `STRONG` chỉ chọn quan hệ mạnh với loader. |
| “`initialize=false` là weak; `true` là strong.” | `initialize` liên quan `<clinit>`, không liên quan chính sách unloading. | Dùng `ClassOption.STRONG` để điều khiển quan hệ unloading. |
| “`NESTMATE` giữ class sống như `STRONG`.” | `NESTMATE` phục vụ quyền truy cập trong nest. | Mỗi `ClassOption` có ý nghĩa riêng. |
| “Cùng bytecode là cùng một class và dùng chung static.” | `defineHiddenClass` tạo danh tính mới ở mỗi lần định nghĩa. | Mỗi hidden class có identity/lifetime riêng. |
| “Đã gán biến `Class` thành `null` là có thể chắc chắn GC.” | `Lookup`, handle, cache, instance, stack và runtime có thể còn giữ lớp. | Rà soát **mọi** nguồn tham chiếu mạnh. |
| “`System.gc()` chứng minh class unload.” | Chỉ là đề nghị GC; thu hồi không có thời điểm bảo đảm. | Dùng logging/monitoring và tránh assert unload đồng bộ. |
| “Có thể đổi weak thành `STRONG` sau khi đã định nghĩa.” | Chính sách dỡ được ấn định tại thời điểm tạo class. | Chọn phương án trước `defineHiddenClass`. |
| “`Class.forName` sẽ tìm được hidden class khi truyền `STRONG`.” | Hidden class không có binary name có thể nạp theo cơ chế thông thường. | Dùng `Lookup`, `Class<?>`, `MethodHandle` đã nhận được. |

Một chi tiết nữa: **unloading độc lập không phải lời hứa về dỡ lớp ngay cả khi có tham chiếu đang sử dụng**. JVM phải giữ ngữ nghĩa an toàn cho chương trình đang chạy.

## 11. Thực hành thiết kế vòng đời hợp lý

Khi viết runtime/framework sinh lớp động:

1. **Xác định quan hệ sống:** Lớp phụ trợ nên tồn tại đến khi một lần gọi kết thúc, đến khi một cache hết hạn, hay trọn vòng đời class loader?
2. **Chọn `ClassOption` có chủ đích:** Dùng mặc định nếu cần khả năng unload sớm; dùng `STRONG` nếu muốn gắn class với loader như class bình thường.
3. **Đừng cache tất cả metadata vô thời hạn:** `Lookup`, `Class<?>` và `MethodHandle` có thể khiến class vẫn reachable.
4. **Tách chính sách khởi tạo:** `initialize=true/false` giải quyết thời điểm chạy mã `static`, không giải quyết thu hồi metadata.
5. **Kiểm thử chức năng trước:** Class được tạo, gọi được method handle, hành vi đúng; sau đó mới đo memory/GC bằng công cụ JVM.
6. **Đo theo điều kiện thực tế:** Tải tạo class, kích thước cache, loader sống bao lâu, mức dùng metaspace và các đợt unloading.
7. **Không dựa vào GC để xử lý side effect nghiệp vụ:** Nếu helper đăng ký callback, giữ tài nguyên hoặc tạo luồng, phải quản lý những tài nguyên đó trực tiếp; class unloading không thay cho quy trình cleanup của ứng dụng.

Chú ý: `defineHiddenClass` cần `Lookup` có quyền **full privilege access** và bytecode có class ở cùng runtime package theo yêu cầu API. Hidden class được tạo để hỗ trợ hoạt động runtime nội bộ; không dùng nó như cách bỏ qua kiểm soát truy cập hoặc thay thế class loader quản lý mô-đun.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một hidden class mặc định có thể bị dỡ trong khi defining loader vẫn được ứng dụng giữ sống không?

**Đáp án:** **Có thể.** Đây là đặc trưng mặc định của hidden class theo API. Nhưng chỉ khi điều kiện liveness cho phép và JVM/GC chọn thực hiện; không có thời điểm bảo đảm.

**Câu 2.** Lớp ẩn có `ClassOption.STRONG` có thể unload độc lập với loader đang reachable không?

**Đáp án:** **Không** theo chính sách `STRONG`. Nó có quan hệ mạnh với defining loader như class thông thường, và có thể được dỡ khi loader không còn reachable, nếu JVM thực hiện unloading.

**Câu 3.** Truyền `initialize=false` có giúp hidden class được unload sớm hơn không?

**Đáp án:** `false` không chọn chính sách unload; nó chỉ tránh yêu cầu khởi tạo ngay trong lời gọi. Để quyết định quan hệ unloading cần xem có truyền `ClassOption.STRONG` hay không.

**Câu 4.** Một cache giữ `MethodHandle` đến phương thức của hidden class thì lớp có chắc được unload khi đã bỏ biến `Class<?>` không?

**Đáp án:** **Không.** Method handle có thể giữ class và metadata liên quan reachable. Cần đánh giá tất cả đường tham chiếu.

**Câu 5.** Chạy `System.gc()` rồi `WeakReference<Class<?>>.get()` vẫn khác `null` có chứng minh tính năng unload độc lập không hoạt động?

**Đáp án:** **Không.** JVM không bảo đảm GC/unloading ngay; cũng có thể còn tham chiếu mạnh. Cần dùng giám sát phù hợp và hiểu điều kiện chạy.

## Ghi nhớ

- **Hidden class mặc định có thể được unload độc lập với defining loader**, ngay cả khi loader vẫn reachable.
- **`ClassOption.STRONG` biến quan hệ unloading thành mạnh như class thông thường**, chỉ có thể unload khi loader đủ điều kiện thu hồi.
- **`initialize`, `NESTMATE` và `STRONG` giải quyết các khía cạnh khác nhau**: khởi tạo, nest access và vòng đời dỡ class.
- **Cùng loader không có nghĩa cùng identity**, và cùng bytecode có thể tạo nhiều hidden class khác nhau.
- **Reachability và hành vi GC quyết định khả năng dỡ thực tế**; `System.gc()` không đảm bảo kết quả, và không nên viết unit test phụ thuộc thời điểm unload.
- **Hidden class mặc định không tự sửa cache hoặc vòng đời tài nguyên thiết kế sai**: hãy quản lý tham chiếu và đo metaspace trong tải thực tế.

### Tài liệu chuẩn còn hiệu lực

- [Oracle Java 15 – MethodHandles.Lookup.ClassOption](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): định nghĩa `STRONG` và quan hệ unloading theo class loader, có từ Java 15.
- [Oracle Java 25 – MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass`, hidden class liveness, các quy tắc riêng về unloading và quyền `Lookup`.
- [Oracle Java 25 – MethodHandles.Lookup.ClassOption](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): ý nghĩa `STRONG` và `NESTMATE` trên JDK hiện đại.
- [Java Language Specification `12.7 – Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.7): nguyên tắc unloading của lớp Java thông thường.
- [OpenJDK JEP 371 – Hidden Classes](https://openjdk.org/jeps/371): lý do tạo hidden class và lựa chọn vòng đời từ Java 15.
