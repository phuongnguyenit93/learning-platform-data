# ClassOption.NESTMATE khi định nghĩa lớp ẩn trong Java 15+

## 1. Bài toán: hidden class có được truy cập thành viên `private` của lớp chủ không?

Từ Java 15, `MethodHandles.Lookup.defineHiddenClass(...)` cho phép JVM định nghĩa **hidden class** từ mảng byte của một class file. Hidden class thường phục vụ những cơ chế sinh mã tại runtime như trình thực thi ngôn ngữ động, proxy hoặc framework; chúng không được tìm lại bằng tên thông thường như `Class.forName(...)`.

Nhưng một hidden class có thể cần gọi phương thức hoặc truy cập trường `private` của lớp tạo ra nó. Java sử dụng cơ chế **nestmate** để cho phép những lớp cùng một **nest** truy cập `private` của nhau. Với hidden class, phải chủ động chọn tùy chọn:

~~~java
MethodHandles.Lookup.ClassOption.NESTMATE
~~~

Tùy chọn này thuộc enum `MethodHandles.Lookup.ClassOption`, có từ Java 15 và vẫn là API được hỗ trợ trong Java hiện hành. Nó cho biết: **đưa hidden class vừa tạo vào nest của lookup class, để hidden class là nestmate với các lớp trong nest đó.**

Ví dụ cú pháp (đoạn minh họa; `classBytes` phải chứa class file hợp lệ):

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandles.Lookup hiddenLookup = lookup.defineHiddenClass(
        classBytes,
        true,
        MethodHandles.Lookup.ClassOption.NESTMATE);

Class<?> hiddenClass = hiddenLookup.lookupClass();
~~~

Không có `NESTMATE`, lời gọi vẫn có thể tạo hidden class thành công, nhưng hidden class **không được đưa vào nest của lớp tra cứu**. Việc nó có quyền truy cập `private` của lớp khác sẽ khác, dù cùng dùng một mảng bytecode.

## 2. Nhắc lại nest và nest host

**Nest** là tập hợp các lớp/interface được JVM xem là cùng nhóm để kiểm tra truy cập thành viên `private`. Mỗi nest có một **nest host** và có thể có nhiều **nest members**.

Ví dụ Java thông thường:

~~~java
class Outer {
    private static String secret() {
        return "hello";
    }

    static class Inner {
        static String readSecret() {
            return secret();
        }
    }
}
~~~

`Outer` và `Outer.Inner` là nestmates. Vì vậy, `Inner` có thể gọi `Outer.secret()` dù phương thức là `private`. Trong Java hiện đại, compiler ghi thông tin nest trong class file (cơ chế nestmate có từ Java 11), và JVM thực hiện kiểm tra truy cập dựa trên quan hệ nest.

Các API quan sát:

~~~java
boolean sameNest = Outer.Inner.class.isNestmateOf(Outer.class);
Class<?> host = Outer.Inner.class.getNestHost();
~~~

Trong ví dụ, `sameNest` là `true` và `host == Outer.class` là `true`.

**Điểm riêng của hidden class:** nó được định nghĩa **động**, không được liệt kê sẵn ở `NestMembers` của class file nest host. `ClassOption.NESTMATE` là cách thông báo cho JVM việc bổ sung thành viên động này.

## 3. `NESTMATE` làm thay đổi điều gì tại thời điểm định nghĩa?

Giả sử `lookup` được tạo bởi `MethodHandles.lookup()` trong lớp `Outer` và `bytes` là bytecode của một lớp thuộc cùng runtime package.

| Gọi API | Hidden class có chung nest với `Outer`? | Có quyền truy cập `private` của `Outer` nhờ nestmate? |
| --- | --- | --- |
| `lookup.defineHiddenClass(bytes, true)` | **Không**; hidden class thuộc nest riêng | **Không** chỉ nhờ việc được tạo bởi `Outer` |
| `lookup.defineHiddenClass(bytes, true, NESTMATE)` | **Có**; thuộc nest của lookup class | **Có**, theo kiểm tra truy cập nestmate của JVM |

`NESTMATE` gắn hidden class vào **nest của lookup class**. Nếu lookup class là một lớp thành viên của nest lớn hơn, hidden class sẽ cùng **nest host của lookup class**, chứ không nhất thiết lấy chính lookup class làm nest host.

Chẳng hạn, nếu `lookup.lookupClass() == Outer.Inner.class` và `Outer.Inner` thuộc nest của `Outer`, hidden class tạo bằng `NESTMATE` cũng có nest host là `Outer`.

Việc thêm `NESTMATE` **không** đổi hidden class thành lớp thông thường:

- `hiddenClass.isHidden()` vẫn trả `true`.
- Tên runtime của hidden class chứa hậu tố do JVM tạo; không nên coi đó là binary name ổn định.
- Không thể tìm hidden class bằng `Class.forName(hiddenClass.getName())`.
- `Class.getNestMembers()` trên nest host **không liệt kê** những hidden class được thêm động bằng `defineHiddenClass`, dù `hiddenClass.isNestmateOf(Outer.class)` trả `true`.

Vì vậy, để kiểm tra quan hệ nest của hidden class đã có đối tượng `Class<?>`, ưu tiên `getNestHost()` và `isNestmateOf()`, **không** suy luận từ việc nó có xuất hiện trong `getNestMembers()` hay không.

## 4. Điều kiện để sử dụng `NESTMATE` thành công

`ClassOption.NESTMATE` **không phải nút bỏ qua mọi kiểm tra quyền**. Điều kiện của `defineHiddenClass(...)` vẫn áp dụng.

### 4.1. `Lookup` phải có full privilege

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

if (!lookup.hasFullPrivilegeAccess()) {
    throw new IllegalStateException("Lookup không đủ quyền");
}
~~~

Một `Lookup` có *full privilege access* khi nó có **đồng thời** mode `PRIVATE` và `MODULE`. `MethodHandles.lookup()` gọi trực tiếp trong code tin cậy thường đáp ứng điều kiện; `MethodHandles.publicLookup()` không đáp ứng.

Nếu không có full privilege, `defineHiddenClass(bytes, true, NESTMATE)` ném `IllegalAccessException`. **Bật `NESTMATE` không biến một `Lookup` yếu thành một `Lookup` mạnh.**

### 4.2. Bytecode phải hợp lệ và cùng runtime package

Bytecode phải biểu diễn một class file hợp lệ. Tên package của lớp được ghi trong class file phải phù hợp với **runtime package của lookup class**. Không thể đưa bytecode thuộc package bất kỳ sang một `Lookup` khác chỉ bằng cách chọn `NESTMATE`.

Ví dụ:

- `Lookup` được tạo tại `com.example.Host` thì class file dùng để định nghĩa hidden class phải có tên lớp thuộc `com.example`.
- Bytecode lỗi, phiên bản class file không được JVM hiện tại hỗ trợ hoặc lỗi liên kết có thể tạo lỗi khác `IllegalAccessException`.
- `NESTMATE` chỉ tác động đến **quan hệ nest**, không thay đổi module của hidden class thành một module tùy ý hay tự mở những package chưa được phép.

Đừng suy luận rằng mọi exception khi tạo hidden class đều do thiếu `NESTMATE`: cần phân biệt lỗi về `Lookup`, package, định dạng class file, xác minh và liên kết.

### 4.3. Lựa chọn `initialize` và `NESTMATE` là hai khái niệm riêng

Trong:

~~~java
lookup.defineHiddenClass(bytes, true, NESTMATE);
~~~

- `true` là tham số `initialize`: yêu cầu khởi tạo hidden class trong lời gọi.
- `NESTMATE` quyết định **quan hệ nest và quyền truy cập private tương ứng**.

Đổi `true` thành `false` không tự cấp/tước nestmate privilege. Tương tự, chọn `NESTMATE` không có nghĩa JVM sẽ chạy mọi static initializer khi tham số `initialize` là `false`.

## 5. Tại sao cùng bytecode, một cách gọi được `private` còn cách kia thất bại?

Khi compiler biên dịch lớp lồng nhau `Template` có lệnh gọi `private` tới lớp bao ngoài, class file thường chứa metadata về nest. Với lớp thông thường, JVM dùng metadata đó để nhận biết quan hệ nest.

Nhưng khi đưa chính class file đó vào `defineHiddenClass(...)`, JVM xác định nest của **hidden class mới** theo tùy chọn của lời gọi:

1. **Có `NESTMATE`:** hidden class được thêm vào nest của lookup class; lệnh gọi `private` đến host có thể vượt qua kiểm tra truy cập theo quan hệ nest.
2. **Không có `NESTMATE`:** hidden class mới **không mặc nhiên giữ quan hệ nest từ class file mẫu**; nếu bytecode cố gọi thành viên `private` của host, JVM sẽ từ chối, điển hình bằng `IllegalAccessError` tại thời điểm liên kết/thực thi lệnh truy cập đó.

Điều này không có nghĩa hidden class không có `NESTMATE` sẽ luôn lỗi: nếu chỉ dùng API được phép truy cập (`public` hoặc các trường hợp truy cập hợp lệ khác) thì nó vẫn có thể hoạt động bình thường.

**Hai loại lỗi khác nhau:**

- `IllegalAccessException` khi gọi `defineHiddenClass` với `Lookup` **không có full privilege**: lỗi ở bước **định nghĩa lớp**.
- `IllegalAccessError` khi hidden class **đã định nghĩa** nhưng bytecode cố truy cập `private` của lớp không cùng nest: lỗi **truy cập ở cấp JVM** khi phương thức liên quan được liên kết/thực thi.

Không viết code chỉ bắt một loại lỗi rồi mặc định nó giải thích mọi tình huống.

## 6. Ví dụ Java đầy đủ — có và không có `NESTMATE`

Ví dụ sau sử dụng một lớp lồng nhau `Template` làm **nguồn class bytes**. `Template` gọi phương thức `private static secret()` của lớp bao ngoài. Chương trình định nghĩa hai hidden class từ **cùng bytecode**: một có `NESTMATE` và một không có.

Lưu tệp đúng tên **`HiddenNestmateDemo.java`**:

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Arrays;

public class HiddenNestmateDemo {
    private static String secret() {
        return "access-granted";
    }

    static class Template {
        public static String readSecret() {
            return secret();
        }

        public static String ping() {
            return "ready";
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        byte[] bytes;
        try (InputStream in = HiddenNestmateDemo.class.getResourceAsStream(
                "HiddenNestmateDemo$Template.class")) {
            if (in == null) throw new IllegalStateException("Template class file missing");
            bytes = in.readAllBytes();
        }

        MethodHandles.Lookup nestLookup = lookup.defineHiddenClass(
                bytes, true, MethodHandles.Lookup.ClassOption.NESTMATE);
        Class<?> mate = nestLookup.lookupClass();
        System.out.println("lookupFull=" + lookup.hasFullPrivilegeAccess());
        System.out.println("mateHidden=" + mate.isHidden());
        System.out.println("mateNestHostOuter=" + (mate.getNestHost() == HiddenNestmateDemo.class));
        System.out.println("mateOfOuter=" + mate.isNestmateOf(HiddenNestmateDemo.class));

        String allowed = (String) nestLookup.findStatic(
                mate, "readSecret", MethodType.methodType(String.class)).invokeExact();
        System.out.println("mateAccess=" + allowed);

        MethodHandles.Lookup plainLookup = lookup.defineHiddenClass(bytes, true);
        Class<?> plain = plainLookup.lookupClass();
        System.out.println("plainHidden=" + plain.isHidden());
        System.out.println("plainNestHostSelf=" + (plain.getNestHost() == plain));
        System.out.println("plainNestmateOfOuter=" + plain.isNestmateOf(HiddenNestmateDemo.class));
        String ping = (String) plainLookup.findStatic(
                plain, "ping", MethodType.methodType(String.class)).invokeExact();
        System.out.println("plainPing=" + ping);

        try {
            String denied = (String) plainLookup.findStatic(
                    plain, "readSecret", MethodType.methodType(String.class)).invokeExact();
            System.out.println("plainPrivateAccess=" + denied);
        } catch (IllegalAccessError expected) {
            System.out.println("plainPrivateAccess=IllegalAccessError");
        }

        System.out.println("listedAsNestMember=" +
                Arrays.asList(HiddenNestmateDemo.class.getNestMembers()).contains(mate));

        try {
            MethodHandles.publicLookup().defineHiddenClass(
                    bytes, true, MethodHandles.Lookup.ClassOption.NESTMATE);
            System.out.println("publicDefine=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("publicDefine=IllegalAccessException");
        }
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 HiddenNestmateDemo.java
java HiddenNestmateDemo
~~~

API `NESTMATE` có từ Java 15; mã trên cũng biên dịch được với `--release 15`. Ví dụ đã được kiểm chứng bằng `javac --release 15`, `javac --release 17` và thực thi trên JDK 24. **Stdout chính xác:**

~~~text
lookupFull=true
mateHidden=true
mateNestHostOuter=true
mateOfOuter=true
mateAccess=access-granted
plainHidden=true
plainNestHostSelf=true
plainNestmateOfOuter=false
plainPing=ready
plainPrivateAccess=IllegalAccessError
listedAsNestMember=false
publicDefine=IllegalAccessException
~~~

### Đọc kết quả như thế nào?

- `lookupFull=true`: quyền của `Lookup` tạo trong lớp host đáp ứng điều kiện định nghĩa hidden class.
- `mateHidden=true`: thêm `NESTMATE` vẫn tạo **hidden class**, không phải class thông thường.
- `mateNestHostOuter=true` và `mateOfOuter=true`: class mới cùng nest với `HiddenNestmateDemo`.
- `mateAccess=access-granted`: bytecode của hidden nestmate gọi thành công `private static secret()` của host.
- `plainHidden=true`: không có `NESTMATE` vẫn có thể tạo hidden class thành công từ bytecode đó.
- `plainNestHostSelf=true` và `plainNestmateOfOuter=false`: hidden class thông thường có nest riêng trong ví dụ này, **không** được kế thừa nest của host.
- `plainPing=ready`: phương thức không cần quyền private vẫn chạy.
- `plainPrivateAccess=IllegalAccessError`: khi thực sự thực thi lệnh truy cập private của host, JVM phát hiện class không thuộc nest của host.
- `listedAsNestMember=false`: `getNestMembers()` không phản ánh các hidden nestmates được thêm động, **không** mâu thuẫn với `mateOfOuter=true`.
- `publicDefine=IllegalAccessException`: `publicLookup()` thiếu full privilege, nên không được dùng để định nghĩa hidden class, dù chỉ định `NESTMATE`.

**Lưu ý về tệp class nguồn:** `javac` tạo `HiddenNestmateDemo.class` và `HiddenNestmateDemo$Template.class` từ cùng file Java. Lệnh `getResourceAsStream(...)` đọc class file thứ hai để minh họa. Ví dụ không tải bytecode từ Internet và không cần thư viện bên ngoài.

## 7. `NESTMATE` khác `STRONG` như thế nào?

Enum `MethodHandles.Lookup.ClassOption` có cả `NESTMATE` và `STRONG`, nhưng hai lựa chọn **độc lập**:

| Tùy chọn | Điều chỉnh | Không tự quyết định |
| --- | --- | --- |
| `NESTMATE` | Thêm hidden class vào nest của lookup class, hỗ trợ truy cập `private` với nestmates | Không tự tạo strong relationship với class loader |
| `STRONG` | Hidden class có quan hệ mạnh với defining class loader, ảnh hưởng điều kiện unload | Không tự thêm hidden class vào nest của lookup class |

Có thể kết hợp hai lựa chọn khi kiến trúc thực sự cần cả hai:

~~~java
MethodHandles.Lookup hiddenLookup = lookup.defineHiddenClass(
        classBytes,
        true,
        MethodHandles.Lookup.ClassOption.NESTMATE,
        MethodHandles.Lookup.ClassOption.STRONG);
~~~

Đây là mã minh họa, với `lookup` và `classBytes` được cung cấp theo các điều kiện tại mục 4. **Không lựa chọn `STRONG` chỉ để sửa lỗi truy cập private** — lỗi đó liên quan đến quan hệ nest. Ngược lại, không lựa chọn `NESTMATE` chỉ vì muốn class được giữ sống lâu hơn.

Việc hidden class có thể được unload không đơn giản là một câu lệnh Java điều khiển trực tiếp; trình thu gom rác và tham chiếu còn tồn tại quyết định khi nào class thực sự được thu hồi. Không dùng `NESTMATE` như một cam kết về thời điểm dọn bộ nhớ.

## 8. Kiểm thử và chẩn đoán lỗi trong dự án

Khi cần hidden class truy cập các thành viên `private` trong nest:

1. **Xác định nest mong muốn:** hãy kiểm tra `lookup.lookupClass()` và `lookup.lookupClass().getNestHost()`. Hidden class sẽ được thêm vào **nest đó** khi chọn `NESTMATE`.
2. **Kiểm tra quyền của `Lookup`:** `lookup.hasFullPrivilegeAccess()` phải là `true` trước khi gọi `defineHiddenClass`.
3. **Kiểm tra class file:** bytecode thuộc đúng package, version và định dạng hỗ trợ, không bị lỗi xác minh hoặc liên kết.
4. **Thêm `ClassOption.NESTMATE` đúng tại lời gọi `defineHiddenClass`** nếu mã sinh ra cần truy cập private của nestmates.
5. **Kiểm tra runtime bằng `hiddenClass.isHidden()`, `getNestHost()`, `isNestmateOf()`**. Không dựa duy nhất vào `getNestMembers()` vì hidden nestmates không nằm trong danh sách trả về.
6. **Phân biệt lỗi:** `IllegalAccessException` lúc định nghĩa thường liên quan quyền `Lookup`; `IllegalAccessError` khi thực thi bytecode có thể do quyền truy cập của class không hợp lệ.
7. **Giữ reference đến hidden class:** dùng `Class<?>`, `MethodHandles.Lookup` hoặc `MethodHandle` trả về, không phụ thuộc vào tên sinh động của JVM.

### Các hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Hidden class tự động là nestmate của lớp định nghĩa nó” | **Không**; cần chỉ rõ `ClassOption.NESTMATE` nếu muốn thêm vào nest |
| “`NESTMATE` tạo ra một lớp bình thường” | **Không**; lớp vẫn là hidden class |
| “Có `NESTMATE` thì mọi `Lookup` đều được phép định nghĩa lớp” | **Không**; `Lookup` vẫn cần full privilege |
| “Hai lớp cùng package là có thể truy cập private của nhau” | **Không**; quyền private ở đây phụ thuộc quan hệ nest, không chỉ package |
| “`getNestMembers()` không thấy hidden class, vậy nó không phải nestmate” | **Sai**; hidden nestmate được thêm động không nằm trong mảng này |
| “Cứ có `NESTMATE` là bytecode khác package vẫn hoạt động” | **Không**; quy tắc runtime package/class file vẫn áp dụng |
| “`STRONG` cấp quyền truy cập private” | **Không**; `STRONG` liên quan vòng đời/quan hệ với class loader |
| “`IllegalAccessException` và `IllegalAccessError` là cùng một lỗi” | **Không**; một loại xảy ra ở API kiểm tra quyền, loại còn lại ở truy cập bytecode do JVM |

### Lưu ý bảo mật

Hidden class có `NESTMATE` **thực sự có khả năng truy cập private** của các nestmates. Đây là quyền mạnh, không phải một hình thức sandbox. Chỉ định nghĩa bytecode được sinh từ **nguồn tin cậy**, không chuyển `Lookup` đầy đủ cho plugin không đáng tin cậy và không chạy class bytes tùy ý từ người dùng dưới một nest có dữ liệu nhạy cảm. Việc giới hạn input, xác minh bytecode, ranh giới module và quyền truy cập vẫn là trách nhiệm của kiến trúc ứng dụng.

## 9. Tự kiểm tra nhanh

**Câu 1.** `lookup.defineHiddenClass(bytes, true)` tạo lớp thành công. Liệu lớp đó chắc chắn gọi được `private` của lookup class? **Không**. Không có `NESTMATE`, nó không được tự động thêm vào nest của lookup class.

**Câu 2.** `mate.isNestmateOf(Host.class)` trả `true` nhưng `Host.class.getNestMembers()` không chứa `mate`. Có lỗi không? **Không**. `getNestMembers()` không liệt kê hidden classes được thêm động.

**Câu 3.** Một `Lookup` tạo bởi `publicLookup()` gọi `defineHiddenClass(bytes, true, NESTMATE)` sẽ được cấp quyền? **Không**. Nó không có full privilege; lời gọi ném `IllegalAccessException`.

**Câu 4.** Một hidden class truy cập private của host bị `IllegalAccessError`, dù lớp được tạo thành công. Trước tiên nên kiểm tra điều gì? **Quan hệ nest của hidden class**, việc có dùng `NESTMATE`, và bytecode đang truy cập thành viên nào.

## Tài liệu chính thức

- Oracle Java SE 26 API, **`MethodHandles.Lookup.ClassOption`**, tài liệu `NESTMATE` và `STRONG`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html
- Oracle Java SE 26 API, **`MethodHandles.Lookup#defineHiddenClass`**: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Oracle Java SE 26 API, **`Class#getNestHost` / `isNestmateOf` / `getNestMembers`**: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html
- OpenJDK, **JEP 371: Hidden Classes** (tính năng chính thức từ Java 15): https://openjdk.org/jeps/371