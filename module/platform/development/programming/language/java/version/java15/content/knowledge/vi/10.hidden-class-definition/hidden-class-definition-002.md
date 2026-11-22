# Điều kiện **full privilege** của `MethodHandles.Lookup` khi định nghĩa hidden class (Java 15+)

## 1. Mục tiêu và khái niệm

Từ **Java 15**, Java cung cấp *hidden class* thông qua `MethodHandles.Lookup.defineHiddenClass(...)` (JEP 371). Đây là lớp được JVM định nghĩa để phục vụ các cơ chế sinh mã và triển khai nội bộ như runtime framework; nó **không được tìm lại bằng tên thông thường** qua `Class.forName(...)` hay `ClassLoader.loadClass(...)`.

Không phải mọi đối tượng `MethodHandles.Lookup` đều được phép định nghĩa hidden class. API yêu cầu `Lookup` **có full privilege access** — quyền truy cập đầy đủ **trong bối cảnh lớp và module mà `Lookup` đại diện**, không phải toàn quyền tùy ý đối với mọi module của JVM.

Điều kiện cốt lõi:

> Một `Lookup` có **full privilege access** khi nó có **đồng thời cả hai mode `PRIVATE` và `MODULE`**.

~~~java
import java.lang.invoke.MethodHandles;

MethodHandles.Lookup lookup = MethodHandles.lookup();

boolean allowed = lookup.hasFullPrivilegeAccess();
int modes = lookup.lookupModes();
int required = MethodHandles.Lookup.PRIVATE | MethodHandles.Lookup.MODULE;
boolean hasRequiredModes = (modes & required) == required;
~~~

Hai biến `allowed` và `hasRequiredModes` đều là `true` đối với `lookup` được tạo trực tiếp trong lớp gọi như trên.

`Lookup.hasFullPrivilegeAccess()` là cách kiểm tra **dễ đọc và đúng mục đích hơn** so với việc tự phân tích bitmask. Phương thức có từ Java 15 và vẫn được hỗ trợ trong Java hiện hành.

## 2. Tại sao phải có cả `PRIVATE` lẫn `MODULE`?

`MethodHandles.Lookup` là một **capability object**: nó mang theo danh tính lớp tra cứu (`lookupClass()`) và các mode cho phép thực hiện kiểm tra truy cập khi tìm method handle, truy cập thành viên hoặc định nghĩa lớp.

| Mode | Vai trò cần hiểu |
| --- | --- |
| `PRIVATE` | Cho phép truy cập private trong phạm vi luật truy cập phù hợp (chẳng hạn nestmates); chứng tỏ quyền tra cứu không chỉ giới hạn ở thành viên public |
| `MODULE` | Chứng tỏ năng lực truy cập cấp module gắn với module của lớp tra cứu, để các phép kiểm tra module đáng tin cậy |
| Cả `PRIVATE` **và** `MODULE` | Đủ điều kiện **full privilege** |
| Thiếu một trong hai | **Không** có full privilege; `defineHiddenClass(...)` bị từ chối bằng `IllegalAccessException` |

Lưu ý quan trọng:

- **Có `PRIVATE` nhưng không có `MODULE` vẫn chưa đủ**. Có thể xảy ra khi `Lookup` được chuyển qua ranh giới module.
- **Có `MODULE` nhưng không có `PRIVATE` cũng chưa đủ**. Quyền truy cập ở cấp module không mặc nhiên cho phép định nghĩa hidden class.
- Các mode như `PUBLIC`, `PACKAGE` hoặc `PROTECTED` **không thay thế** yêu cầu đồng thời `PRIVATE` và `MODULE`.
- `lookupModes()` là bitmask. Không kiểm tra bằng `modes == PRIVATE | MODULE`: `Lookup` đầy đủ thường còn những mode khác. Dùng `hasFullPrivilegeAccess()` hoặc phép `(modes & required) == required`.

Khái niệm `full privilege` **không đồng nghĩa** với mode `ORIGINAL` được cung cấp trong các phiên bản Java mới hơn: một `Lookup` tạo bởi `privateLookupIn` trong **cùng module** có thể có full privilege dù không phải `Lookup` nguyên bản từ lời gọi `MethodHandles.lookup()`. Để gọi `defineHiddenClass`, điều kiện cần xét ở đây là **full privilege**, không phải bắt buộc có `ORIGINAL`.

## 3. Những nguồn `Lookup` thường gặp

### 3.1. `MethodHandles.lookup()` — có đầy đủ quyền của lớp gọi

~~~java
MethodHandles.Lookup full = MethodHandles.lookup();

System.out.println(full.hasFullPrivilegeAccess()); // true
~~~

`MethodHandles.lookup()` là phương thức *caller-sensitive*: `Lookup` trả về gắn với **lớp trực tiếp gọi** phương thức đó. Nó có full privilege đối với bối cảnh lớp gọi và module của lớp gọi, không tự động mở các package của module khác.

Đây là lựa chọn thông thường khi một lớp tin cậy định nghĩa hidden class từ bytecode trong **cùng runtime package**.

### 3.2. `MethodHandles.publicLookup()` — không đủ quyền

~~~java
MethodHandles.Lookup pub = MethodHandles.publicLookup();

System.out.println(pub.hasFullPrivilegeAccess()); // false
~~~

`publicLookup()` chỉ có quyền công khai giới hạn; vì không có cặp `PRIVATE` và `MODULE`, nó không đủ quyền cho `defineHiddenClass`.

### 3.3. `dropLookupMode(...)` — đã mất quyền thì không lấy lại bằng phép gọi này

~~~java
MethodHandles.Lookup full = MethodHandles.lookup();
MethodHandles.Lookup noPrivate =
        full.dropLookupMode(MethodHandles.Lookup.PRIVATE);
MethodHandles.Lookup noModule =
        full.dropLookupMode(MethodHandles.Lookup.MODULE);

System.out.println(noPrivate.hasFullPrivilegeAccess()); // false
System.out.println(noModule.hasFullPrivilegeAccess());  // false
~~~

`dropLookupMode` **giảm** quyền của `Lookup`. Xóa `PRIVATE` hoặc `MODULE` làm mất điều kiện đầy đủ, bất kể những bit truy cập khác còn lại ra sao. Không nên dựa vào một `Lookup` đã bị giới hạn để tiếp tục định nghĩa hidden class.

### 3.4. `privateLookupIn` — phải xét **cùng module hay khác module**

~~~java
MethodHandles.Lookup local = MethodHandles.privateLookupIn(
        SomeClass.class, MethodHandles.lookup());
~~~

Đây là **đoạn minh họa**, giả định `SomeClass` là lớp hợp lệ và phù hợp các điều kiện kiểm tra truy cập. Nếu `SomeClass` nằm **cùng module** và `Lookup` đầu vào có full privilege, `Lookup` kết quả có full privilege đối với `SomeClass`.

Nếu tra cứu **qua module khác**, dù đủ điều kiện thực hiện deep reflection và `privateLookupIn` thành công, `Lookup` kết quả sẽ **mất mode `MODULE`**, nên **không còn full privilege**. Chi tiết được giải thích trong mục 5.

## 4. `defineHiddenClass` kiểm tra full privilege như thế nào?

Chữ ký chủ đạo:

~~~java
MethodHandles.Lookup hiddenLookup = lookup.defineHiddenClass(
        classBytes,
        true,
        MethodHandles.Lookup.ClassOption.NESTMATE);
~~~

Đây là **đoạn minh họa**: `lookup` phải được tạo hợp lệ, `classBytes` phải chứa một class file hợp lệ và tùy chọn `NESTMATE` chỉ nên dùng khi thực sự cần quan hệ nestmate với lớp tra cứu. Không bắt buộc chọn `NESTMATE` để định nghĩa hidden class.

Tham số:

- `classBytes`: mảng byte của một **class file** đã biên dịch, không phải mã nguồn Java hay tên lớp.
- `initialize`: tham số boolean; `true` yêu cầu khởi tạo lớp mới; `false` không yêu cầu khởi tạo ngay trong lời gọi.
- `options`: các `ClassOption` tùy chọn, ví dụ `NESTMATE` nếu cần quan hệ nestmate và quyền private tương ứng.
- Kết quả là một **`Lookup` mới đặt trên hidden class**, chứ không trực tiếp là `Class<?>`. Lấy `Class<?>` bằng `hiddenLookup.lookupClass()`.

**Điều kiện cần:** `lookup.hasFullPrivilegeAccess() == true`. Nếu `Lookup` thiếu quyền, `defineHiddenClass(...)` ném **`IllegalAccessException`**, không tự động yêu cầu mở quyền hoặc tự tìm `Lookup` khác.

**Nhưng full privilege chưa đủ cho mọi bytecode**: bytecode vẫn phải là class file hợp lệ, có phiên bản class file JVM hỗ trợ, và **tên package khai báo trong bytecode phải tương ứng với package của lookup class**. Nếu class file thuộc package khác, có thể nhận `IllegalArgumentException`; class file không hợp lệ có thể nhận `ClassFormatError`, chưa kể các lỗi liên kết/xác minh khác. Không coi mọi lỗi `defineHiddenClass` là do thiếu quyền.

Hidden class được định nghĩa trong **cùng runtime package** và trong bối cảnh module của lớp tra cứu. Đối với hidden class có tên được JVM tạo thêm phần hậu tố đặc biệt, **đừng dựa vào tên đầy đủ làm định danh ổn định**: giữ `Class<?>` hoặc `MethodHandle` trả về từ lần định nghĩa.

## 5. Ranh giới module: `privateLookupIn` không tự cấp full privilege xuyên module

Giả sử:

~~~text
Module M1: lớp Factory tạo MethodHandles.lookup()
Module M2: lớp Target nằm trong package p
~~~

Để `MethodHandles.privateLookupIn(Target.class, lookupM1)` được phép tra cứu private xuyên module, thông thường cần:

1. `lookupM1` đầu vào có **cả `MODULE` và `PRIVATE`** (full privilege).
2. M1 **đọc** M2 (`requires` hoặc quan hệ readability thích hợp).
3. M2 **mở** package `p` cho M1 (`opens p to M1;` hoặc hình thức mở tương đương).

Nếu thiếu các điều kiện này, `privateLookupIn` có thể ném `IllegalAccessException`.

**Kể cả khi cả ba điều kiện thỏa mãn**, `Lookup` trả về cho `Target` trong M2 có `PRIVATE` nhưng **không có `MODULE`**, nên `hasFullPrivilegeAccess()` trả `false`. Vì thế không thể dùng chính `Lookup` đó để gọi `defineHiddenClass(...)` — yêu cầu full privilege vẫn tồn tại.

| Tình huống | `Lookup` kết quả | Có thể gọi `defineHiddenClass` chỉ dựa trên full privilege? |
| --- | --- | --- |
| `MethodHandles.lookup()` tại lớp tin cậy | Full privilege | **Có**, nếu bytecode và package hợp lệ |
| `privateLookupIn` tới lớp khác **cùng module** | Full privilege (khi tiền điều kiện đạt) | **Có**, nếu bytecode/package hợp lệ |
| `privateLookupIn` tới lớp ở **module khác**, có quyền mở package | Có thể có private, **mất MODULE** | **Không** |
| `lookup.in(OtherModuleClass.class)` qua module khác | Các mode bị giảm, **mất MODULE** | **Không** |
| `publicLookup()` | Quyền công khai giới hạn | **Không** |

**`exports` khác `opens`**: export public API không đồng nghĩa cho phép deep reflection vào private; nhưng ngay cả một package đã mở vẫn không biến `Lookup` của module khác thành full-privileged `Lookup` cho hidden class.

Muốn định nghĩa hidden class trong package/module đích, hãy thiết kế **factory tin cậy đặt trong chính module đích**, để mã trong module đó gọi `MethodHandles.lookup()` trong bối cảnh có full privilege và xác nhận bytecode hợp lệ. Không coi `setAccessible(true)`, thêm `--add-opens` hoặc chuyển `Lookup` xuyên module là cách thay thế điều kiện `PRIVATE + MODULE`.

## 6. Ví dụ hoàn chỉnh (Java 15+) kiểm chứng quyền và tạo hidden class

Chương trình dưới đây không cần framework hay thư viện ngoài. Nó sử dụng file class của một lớp `Template` được biên dịch cùng nguồn làm dữ liệu bytecode. Cả chương trình và `Template` nằm trong **unnamed package** để ví dụ tập trung vào điều kiện quyền; trong dự án có package, cần giữ nguyên tắc **cùng package** giữa `Lookup` và bytecode.

Lưu đúng tên file: **`HiddenClassPrivilegeDemo.java`**.

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HiddenClassPrivilegeDemo {
    public static class Template {
        public static String message() {
            return "Hello from hidden class";
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup full = MethodHandles.lookup();
        MethodHandles.Lookup pub = MethodHandles.publicLookup();
        MethodHandles.Lookup noPrivate =
                full.dropLookupMode(MethodHandles.Lookup.PRIVATE);
        MethodHandles.Lookup noModule =
                full.dropLookupMode(MethodHandles.Lookup.MODULE);
        MethodHandles.Lookup sameModule =
                MethodHandles.privateLookupIn(Template.class, full);
        MethodHandles.Lookup acrossModules = full.in(String.class);

        System.out.println("full=" + full.hasFullPrivilegeAccess());
        System.out.println("public=" + pub.hasFullPrivilegeAccess());
        System.out.println("noPrivate=" + noPrivate.hasFullPrivilegeAccess());
        System.out.println("noModule=" + noModule.hasFullPrivilegeAccess());
        System.out.println("sameModule=" + sameModule.hasFullPrivilegeAccess());
        System.out.println("acrossModules=" + acrossModules.hasFullPrivilegeAccess());
        System.out.println("fullHasPrivateModule=" + hasPrivateModule(full));
        System.out.println("noPrivateHasPrivateModule=" + hasPrivateModule(noPrivate));

        byte[] bytes;
        try (InputStream in = HiddenClassPrivilegeDemo.class.getResourceAsStream(
                "HiddenClassPrivilegeDemo$Template.class")) {
            if (in == null) {
                throw new IllegalStateException("Template class resource is missing");
            }
            bytes = in.readAllBytes();
        }

        try {
            pub.defineHiddenClass(bytes, true);
            System.out.println("publicDefine=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("publicDefine=IllegalAccessException");
        }

        try {
            noPrivate.defineHiddenClass(bytes, true);
            System.out.println("noPrivateDefine=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("noPrivateDefine=IllegalAccessException");
        }

        try {
            noModule.defineHiddenClass(bytes, true);
            System.out.println("noModuleDefine=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("noModuleDefine=IllegalAccessException");
        }

        MethodHandles.Lookup hiddenLookup = full.defineHiddenClass(bytes, true);
        Class<?> hiddenClass = hiddenLookup.lookupClass();
        String result = (String) hiddenLookup.findStatic(
                hiddenClass, "message", MethodType.methodType(String.class))
                .invokeExact();

        System.out.println("hidden=" + hiddenClass.isHidden());
        System.out.println("hiddenLookupFull=" + hiddenLookup.hasFullPrivilegeAccess());
        System.out.println("hiddenNameHasSlash=" + hiddenClass.getName().contains("/"));
        System.out.println("message=" + result);

        try {
            Class.forName(hiddenClass.getName());
            System.out.println("classForName=found");
        } catch (ClassNotFoundException expected) {
            System.out.println("classForName=notFound");
        }
    }

    private static boolean hasPrivateModule(MethodHandles.Lookup lookup) {
        int modes = lookup.lookupModes();
        int required = MethodHandles.Lookup.PRIVATE | MethodHandles.Lookup.MODULE;
        return (modes & required) == required;
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 HiddenClassPrivilegeDemo.java
java HiddenClassPrivilegeDemo
~~~

Có thể thay `--release 17` bằng `--release 15`: toàn bộ API trong chương trình đã có ở Java 15. Bài đã được kiểm chứng bằng `javac --release 15`, `javac --release 17` và JVM JDK 24. Đầu ra chính xác:

~~~text
full=true
public=false
noPrivate=false
noModule=false
sameModule=true
acrossModules=false
fullHasPrivateModule=true
noPrivateHasPrivateModule=false
publicDefine=IllegalAccessException
noPrivateDefine=IllegalAccessException
noModuleDefine=IllegalAccessException
hidden=true
hiddenLookupFull=true
hiddenNameHasSlash=true
message=Hello from hidden class
classForName=notFound
~~~

### Giải thích các kết quả cần quan sát

- `full=true`: `MethodHandles.lookup()` của chính lớp chạy có đầy đủ quyền.
- `sameModule=true`: `privateLookupIn(Template.class, full)` lấy `Lookup` khác nhưng vẫn **full privilege**, vì hai lớp trong cùng module và quyền đầu vào phù hợp.
- `acrossModules=false`: `String` thuộc module `java.base`, còn ví dụ chạy trong unnamed module. `full.in(String.class)` đi qua module khác và mất `MODULE`. Đây là ví dụ kiểm tra quyền, **không** gọi `privateLookupIn(String.class, ...)`.
- Ba dòng `...Define=IllegalAccessException`: `publicLookup`, `noPrivate` và `noModule` không đáp ứng full privilege.
- `hidden=true` và `message=Hello from hidden class`: cùng `Lookup` đầy đủ có thể định nghĩa hidden class hợp lệ rồi gọi method `message` qua `MethodHandle`.
- `hiddenLookupFull=true`: `Lookup` trả về trên hidden class có full privilege. Tuy nhiên, điều đó không có nghĩa hidden class có quyền vô hạn ở mọi module.
- `hiddenNameHasSlash=true`: tên runtime của hidden class mang hậu tố do JVM tạo; chương trình tránh in cả tên vì hậu tố không cố định.
- `classForName=notFound`: không thể truy hồi hidden class bằng tên qua cơ chế tìm lớp thông thường.

**Vì sao đọc file `$Template.class`?** Lệnh `javac` tạo cả `HiddenClassPrivilegeDemo.class` và `HiddenClassPrivilegeDemo$Template.class`. `getResourceAsStream(...)` đọc byte của lớp mẫu để minh họa `defineHiddenClass`. Đây không phải việc tạo bytecode bằng tay và không đòi tệp ngoài tệp `.java` đã biên dịch.

## 7. Chẩn đoán lỗi và thực hành an toàn

### 7.1. Khi nhận `IllegalAccessException`

Kiểm tra theo thứ tự:

1. `lookup.hasFullPrivilegeAccess()` có `true` không?
2. Nếu `false`, `lookup.lookupModes()` có đủ `PRIVATE` và `MODULE` không?
3. `Lookup` đến từ đâu: `MethodHandles.lookup()` trực tiếp, `publicLookup()`, `dropLookupMode`, `Lookup.in`, hay `privateLookupIn`?
4. Nó có đi qua **ranh giới module** hay bị hạn chế quyền trước đó không?
5. Nếu phải tạo hidden class ở module đích, kiến trúc có thể chuyển trách nhiệm tạo lớp sang một **factory đáng tin trong module đích** không?

Nếu `hasFullPrivilegeAccess() == true` mà vẫn thất bại, hãy xem **loại exception và nguyên nhân thực tế**: bytecode không hợp lệ, sai package, class file quá mới hoặc vấn đề liên kết có thể là lỗi **khác `IllegalAccessException`**.

### 7.2. Phân biệt quyền gọi API và quyền của hidden class

- **Full privilege của `Lookup`** là yêu cầu cho *thao tác định nghĩa hidden class*.
- **`ClassOption.NESTMATE`** là tùy chọn điều chỉnh quan hệ nestmate của hidden class; nó **không tự cấp full privilege cho `Lookup` gọi API**.
- Truy cập private giữa hidden class và lớp host, phương thức gọi được, class data hay initialize behavior có điều kiện riêng. Đừng suy luận rằng chỉ vì tạo thành công hidden class thì mọi quyền truy cập đến module khác cũng được cho phép.
- Khi định nghĩa class từ bytecode không tin cậy, cần xem xét cẩn thận: việc trao cho nó khả năng chạy trong module/runtime package của ứng dụng làm tăng bề mặt bảo mật. **Không đưa `Lookup` có full privilege cho mã bên thứ ba không tin cậy** và không chấp nhận bytecode tùy ý từ đầu vào thiếu xác thực.

### 7.3. Các ngộ nhận phổ biến

| Ngộ nhận | Điều đúng |
| --- | --- |
| “`publicLookup()` cũng định nghĩa hidden class được vì lớp tạo ra public” | **Không**; hidden-class definition yêu cầu full privilege ngay tại API |
| “Chỉ `PRIVATE` là đủ” | **Không**; còn phải có `MODULE` |
| “Chỉ `MODULE` là đủ” | **Không**; còn phải có `PRIVATE` |
| “`privateLookupIn` luôn tạo full privilege” | **Không** khi xuyên module: kết quả mất `MODULE` |
| “`exports`/`opens` cho module khác là đủ để định nghĩa hidden class bên đó” | **Không**; mở package phục vụ truy cập nhưng không làm `Lookup` xuyên module có full privilege |
| “`NESTMATE` sẽ vượt kiểm tra quyền” | **Không**; tùy chọn này không thay yêu cầu của `Lookup` |
| “Có `full privilege` thì định nghĩa bytecode nào cũng được” | **Không**; còn phải đúng package, định dạng class file và các ràng buộc liên kết |
| “`Class.forName(hidden.getName())` sẽ tìm lại lớp” | **Không**; hidden class không được truy tìm qua tên thông thường |

## 8. Tóm tắt để ghi nhớ

- **`full privilege = PRIVATE + MODULE`** trên cùng `MethodHandles.Lookup`.
- Kiểm tra bằng **`lookup.hasFullPrivilegeAccess()`**.
- **`Lookup.defineHiddenClass(...)` cần full privilege**, thiếu sẽ ném **`IllegalAccessException`**.
- `MethodHandles.lookup()` tại code tin cậy cung cấp full privilege trong bối cảnh lớp gọi.
- `publicLookup()` và các `Lookup` đã bị rút quyền không dùng được.
- `privateLookupIn` sang lớp **cùng module** có thể giữ full privilege; qua **module khác** sẽ mất `MODULE`, kể cả khi package được mở cho deep reflection.
- Full privilege là **điều kiện cần, không phải điều kiện đủ**: bytecode/package và bảo mật cũng quan trọng.

## Tài liệu chính thức

- Oracle Java SE 25, **`MethodHandles.Lookup`** — access modes, `hasFullPrivilegeAccess`, `defineHiddenClass`, `dropLookupMode`, `lookupModes`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Oracle Java SE 25, **`MethodHandles`** — `lookup`, `publicLookup`, `privateLookupIn` và quy tắc cross-module: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html
- OpenJDK, **JEP 371: Hidden Classes** — tính năng chính thức từ Java 15: https://openjdk.org/jeps/371