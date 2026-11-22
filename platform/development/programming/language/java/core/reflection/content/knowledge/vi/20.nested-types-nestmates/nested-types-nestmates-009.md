# Hidden class, `Class.isHidden()` và giới hạn khám phá bằng `Class.forName()`

## 1. Mục tiêu và vị trí trong chủ đề kiểu lồng, nest

Sau bài này, bạn có thể:

- Phân biệt **hidden class** với lớp có tên thông thường, lớp lồng (nested class), lớp cục bộ (local class) và lớp vô danh (anonymous class).
- Tạo hidden class từ bytecode bằng `MethodHandles.Lookup.defineHiddenClass(...)` và nhận lại đối tượng `Class<?>` của nó.
- Dùng `Class.isHidden()` để nhận diện đúng hidden class; giải thích vì sao `Class.forName(hidden.getName())` không thể tìm ra lớp này.
- Hiểu mối liên hệ giữa **nest**, **nestmate**, tùy chọn `NESTMATE` và giới hạn của `getNestMembers()` khi có hidden class.
- Biết cách thiết kế mã reflection/framework khi lớp được tạo động không thể được tra cứu lại từ chuỗi tên.

**Phạm vi:** Java 17 trở lên (các API hidden class xuất hiện từ Java 15). Bài này tập trung vào cơ chế nhận diện và khám phá lớp trong Reflection, không đi sâu vào tự sinh mã bytecode hay viết class loader.

## 2. Hidden class là gì?

Một **hidden class** là lớp/interface được JVM định nghĩa tại thời điểm chạy từ một mảng bytecode thông qua API như `MethodHandles.Lookup.defineHiddenClass(...)`. Hidden class có đối tượng `Class<?>` thực sự, có thể có constructor, method, field, instance và có thể được thao tác bằng Reflection khi mã gọi có quyền truy cập phù hợp.

Điểm khác biệt quyết định: hidden class **không có binary name hợp lệ để các lớp khác tham chiếu tượng trưng**. Vì vậy, các thao tác tìm lớp theo tên thông thường, bao gồm `Class.forName(...)` và `ClassLoader.loadClass(...)`, không thể khám phá lại hidden class.

“Hidden” **không** có nghĩa là bí mật hay bất khả xâm phạm: ai đang giữ tham chiếu `Class<?>`, một `MethodHandles.Lookup` phù hợp hoặc instance có thể tương tác với lớp tùy theo quyền truy cập. Nó cũng không có nghĩa “khai báo `private`”, “lớp vô danh” hay “lớp lồng”. Các đặc điểm đó là những khái niệm độc lập.

| Kiểu | Có tên để `Class.forName` tra cứu? | `Class.isHidden()` | Ghi chú |
| --- | --- | --- | --- |
| Lớp top-level `Example` | Có, nếu class loader tìm được | `false` | Lớp thông thường |
| Lớp lồng `Outer.Inner` | Có, bằng **binary name** như `Outer$Inner` | `false` | Dấu chấm trong tên nguồn Java không phải tên binary của member class |
| Lớp local hoặc anonymous do `javac` tạo | Có thể có tên nhị phân do compiler phát sinh, không ổn định để làm API | `false` | Không tự động trở thành hidden class |
| Lớp do `defineHiddenClass` tạo | **Không** | `true` | Phải giữ `Class<?>`/lookup/handle được trả về |

Ví dụ, `Outer.Inner.class.getName()` thường là `"Outer$Inner"` (nếu cùng default package). Với hidden class, `getName()` thường có dạng `"Outer$Template/0x..."`: phần hậu tố do JVM sinh ra và **không làm chuỗi đó trở thành binary name có thể tra cứu**.

## 3. Cơ chế tạo và các API cốt lõi

```java
MethodHandles.Lookup callerLookup = MethodHandles.lookup();

MethodHandles.Lookup hiddenLookup = callerLookup.defineHiddenClass(
    classFileBytes,
    true,
    MethodHandles.Lookup.ClassOption.NESTMATE
);

Class<?> hiddenType = hiddenLookup.lookupClass();
boolean hidden = hiddenType.isHidden();
```

Đoạn trên minh họa lời gọi API; biến `classFileBytes` phải chứa **bytecode của một class file hợp lệ**, đã được biên dịch hoặc sinh ra trước đó.

- `defineHiddenClass(byte[] bytes, boolean initialize, ClassOption... options)` định nghĩa một lớp mới từ nội dung class file và trả về `Lookup` với **lookup class chính là hidden class** mới tạo. Nó không đưa lớp vào cơ chế tra cứu tên của class loader.
- `initialize = true` yêu cầu JVM khởi tạo lớp vừa định nghĩa; `false` không yêu cầu khởi tạo ngay tại bước này. Khởi tạo sau đó vẫn có thể xảy ra theo quy tắc JVM bình thường.
- Lookup gọi hàm phải có **full-privilege access**; lớp trong bytecode phải ở **cùng runtime package** với lookup class. Không thể lấy bytecode của một package bất kỳ rồi dùng lookup bất kỳ để định nghĩa.
- `Class.isHidden()` trả về `true` khi và chỉ khi `Class<?>` biểu diễn hidden class; việc tên trông lạ, có `$`, hay khai báo `private` **không phải** tiêu chí thay thế.
- `Class.getCanonicalName()` của hidden class trả về `null`. `getName()` vẫn trả về một chuỗi nhận diện ở runtime, nhưng không phải binary name dùng cho `forName`.
- `Class.forName(String)` hoặc phiên bản có `ClassLoader` tìm lớp bằng binary name. Không có overload nào biến hidden class thành lớp có thể tìm lại bằng tên.

Hai tùy chọn hữu ích của `Lookup.ClassOption`:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `NESTMATE` | Đưa hidden class vào **cùng nest** với lookup class; cho phép quyền truy cập `private` giữa nestmates theo quy tắc JVM |
| `STRONG` | Gắn vòng đời hidden class mạnh với defining class loader, tương tự lớp thông thường |

Mặc định nếu không có `NESTMATE`, hidden class tạo thành nest riêng có chính nó là nest host. Nếu không có `STRONG`, JVM *có thể* dỡ hidden class ngay cả khi defining loader còn sống, miễn không còn tham chiếu giữ lớp lại. Việc GC/unloading diễn ra lúc nào không được bảo đảm.

## 4. Ví dụ hoàn chỉnh: cùng bytecode, một lớp có tên và một hidden class

Tạo file **`HiddenClassDemo.java`** với nội dung:

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.util.Arrays;

public class HiddenClassDemo {
    private static String secret() {
        return "nest-secret";
    }

    public static class Template {
        public String greeting() {
            return "Hello from hidden class";
        }

        public String readHostSecret() {
            return HiddenClassDemo.secret();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytecode;
        try (InputStream in =
                     Template.class.getResourceAsStream("HiddenClassDemo$Template.class")) {
            if (in == null) {
                throw new IllegalStateException("Missing compiled Template.class");
            }
            bytecode = in.readAllBytes();
        }

        MethodHandles.Lookup hiddenLookup = MethodHandles.lookup().defineHiddenClass(
                bytecode, true, MethodHandles.Lookup.ClassOption.NESTMATE);
        Class<?> hidden = hiddenLookup.lookupClass();
        Object obj = hidden.getDeclaredConstructor().newInstance();

        System.out.println("Template hidden: " + Template.class.isHidden());
        System.out.println("Dynamic hidden: " + hidden.isHidden());
        System.out.println("Nestmate of host: "
                + hidden.isNestmateOf(HiddenClassDemo.class));
        System.out.println("Nest host is outer: "
                + (hidden.getNestHost() == HiddenClassDemo.class));
        System.out.println("In getNestMembers: "
                + Arrays.asList(HiddenClassDemo.class.getNestMembers()).contains(hidden));
        System.out.println("Has canonical name: " + (hidden.getCanonicalName() != null));
        System.out.println("Named template can be found: "
                + (Class.forName(Template.class.getName()) == Template.class));

        try {
            Class.forName(hidden.getName());
            System.out.println("Hidden class found unexpectedly");
        } catch (ClassNotFoundException expected) {
            System.out.println("Hidden class via Class.forName: NOT FOUND");
        }

        System.out.println("Method call: "
                + hidden.getDeclaredMethod("greeting").invoke(obj));
        System.out.println("Private host access: "
                + hidden.getDeclaredMethod("readHostSecret").invoke(obj));
    }
}
```

Trong thư mục chứa file, chạy bằng **JDK 17+**:

```bash
javac --release 17 HiddenClassDemo.java
java HiddenClassDemo
```

Kết quả:

```text
Template hidden: false
Dynamic hidden: true
Nestmate of host: true
Nest host is outer: true
In getNestMembers: false
Has canonical name: false
Named template can be found: true
Hidden class via Class.forName: NOT FOUND
Method call: Hello from hidden class
Private host access: nest-secret
```

**Giải thích từng hiện tượng:**

1. `javac` sinh `HiddenClassDemo.class` và `HiddenClassDemo$Template.class`. `Template` là một **static nested class thông thường**: `Template.class.isHidden() == false`; `Class.forName(Template.class.getName())` tìm đúng lớp có tên.
2. `getResourceAsStream(...)` đọc **bytecode** của `Template`, không chỉ chuỗi tên. `defineHiddenClass` dùng bytecode đó để JVM định nghĩa **một `Class<?>` khác**, có danh tính khác với `Template.class`.
3. `hidden.isHidden()` trả về `true` dù bytecode bắt nguồn từ class file vốn có tên. Danh tính của lớp được tạo mới do API định nghĩa hidden class quyết định.
4. `NESTMATE` đưa hidden class vào nest của `HiddenClassDemo`. Do đó `hidden.isNestmateOf(HiddenClassDemo.class)` và phép so `hidden.getNestHost() == HiddenClassDemo.class` đều `true`.
5. Hidden class **không xuất hiện** trong danh sách `HiddenClassDemo.class.getNestMembers()`. Hàm đó duyệt nest members ghi trong metadata `NestMembers` của class file; các hidden nestmate thêm ở runtime không nằm trong danh sách liệt kê này.
6. `hidden.getCanonicalName() == null`. `Class.forName(hidden.getName())` thất bại với `ClassNotFoundException`; đây là kết quả **mong đợi**, không phải lỗi cấu hình classpath.
7. Vẫn có thể tạo instance và gọi method qua `hidden.getDeclaredConstructor()`, `getDeclaredMethod(...)` vì chương trình **đang giữ trực tiếp** `Class<?> hidden`. Method `readHostSecret()` đọc thành viên `private` của host thành công nhờ quan hệ nestmate.

**Đã kiểm chứng:** mã trên biên dịch ở chế độ `--release 17` và chạy ra đúng các dòng kết quả trên bằng JDK 21. Chuỗi tên cụ thể từ `hidden.getName()` được cố ý không in ra vì hậu tố do JVM cấp có thể thay đổi mỗi lần chạy.

## 5. Phân biệt “biết lớp tồn tại” và “tìm lớp theo tên”

Với lớp thông thường:

```java
String binaryName = HiddenClassDemo.Template.class.getName();
Class<?> named = Class.forName(binaryName);
System.out.println(named == HiddenClassDemo.Template.class); // true
```

Với hidden class:

```java
Class<?> hidden = hiddenLookup.lookupClass(); // hiddenLookup từ phần trước
String runtimeName = hidden.getName();
Class<?> resolved = Class.forName(runtimeName); // ném ClassNotFoundException
```

Đoạn thứ hai **chỉ là minh họa sự thất bại**, không phải chương trình hoàn chỉnh để chạy độc lập. Không nên viết `Class.forName(...)` ngoài `try/catch` như một chiến lược khôi phục lớp hidden.

Quy tắc cần ghi nhớ:

- **Có tham chiếu `Class<?>`:** có thể dùng Reflection trên đối tượng đó, với kiểm tra quyền truy cập bình thường.
- **Chỉ có chuỗi `getName()`:** không thể truy xuất lại hidden class qua `Class.forName`, kể cả khi dùng đúng class loader.
- **Có `Lookup` trả về:** có thể thao tác với lớp vừa tạo qua `lookupClass()` và dùng method handle tương ứng, nếu quyền cho phép.
- **Chỉ quét `getDeclaredClasses()` hoặc `getNestMembers()` của host:** không thể suy luận rằng đã tìm đủ hidden classes được định nghĩa động. `getDeclaredClasses()` nói về member classes ghi trong class metadata; `getNestMembers()` bỏ qua hidden nestmates được thêm khi chạy.

Một hệ thống plugin/serializer/reflection scanner chỉ lưu `class.getName()` rồi gọi `Class.forName(name)` về sau sẽ không tương thích với hidden class. Nếu thực sự cần hỗ trợ loại này, hãy giữ tham chiếu runtime thích hợp trong vòng đời sử dụng (ví dụ `Class<?>`, `Lookup`, factory hoặc `MethodHandle`), thay vì thiết kế hợp đồng chỉ dựa vào tên.

## 6. Hidden class và nestmate: quan hệ chính xác

**Nest** là nhóm class/interface trong cùng runtime package có thể truy cập thành viên `private` của nhau. Với nested classes biên dịch thông thường, compiler ghi quan hệ qua thuộc tính `NestHost`/`NestMembers`. Với hidden class, `NESTMATE` thiết lập quan hệ động thông qua JVM mà **không sửa metadata `NestMembers` của host**.

Ba câu hỏi sau có đáp án khác nhau:

| Câu hỏi | API | Kết quả với hidden class dùng `NESTMATE` |
| --- | --- | --- |
| Đây có phải hidden class? | `hidden.isHidden()` | `true` |
| Đây có phải nestmate của host? | `hidden.isNestmateOf(Host.class)` | `true` nếu cùng nest |
| Host liệt kê được lớp này? | `Arrays.asList(Host.class.getNestMembers()).contains(hidden)` | `false` |

Không nên nhầm **quan hệ thành viên thực tế** (câu 2) với **khả năng liệt kê** (câu 3). `getNestMembers()` trả về những thành viên nest có tên được ghi trong class file, **không bao gồm hidden classes được thêm bằng `defineHiddenClass`**.

Nếu bỏ `NESTMATE` khỏi ví dụ, hidden class mặc định ở nest riêng. Đoạn bytecode gọi `HiddenClassDemo.secret()` (method `private`) không còn được cấp quyền nestmate, nên thao tác gọi method đó có thể gặp lỗi liên kết/truy cập như `IllegalAccessError`. Lưu ý: đây là lỗi quyền truy cập bytecode khi thực thi, không phải `ClassNotFoundException` của `forName`.

## 7. Ứng dụng thực tế và giới hạn

Hidden classes thích hợp cho hệ thống sinh mã lúc chạy, ví dụ lớp hỗ trợ triển khai lambda hoặc lớp nội bộ do framework sinh ra không cần được tham chiếu bằng tên nhị phân từ mã ứng dụng. Chúng giúp giảm nhu cầu giữ một namespace tên lớp có thể khám phá, đồng thời có thể hỗ trợ dỡ lớp linh hoạt hơn khi không dùng `STRONG`.

Khi thiết kế thư viện dùng Reflection:

1. **Chọn cơ chế khám phá phù hợp.** Với lớp công khai do người dùng cấu hình theo tên, dùng lớp có binary name ổn định. Với lớp nội bộ sinh động, trả lại `Class<?>`/factory/handle ngay từ nơi tạo.
2. **Không dùng tên hiển thị như khóa khôi phục.** `hidden.getName()` có thể hữu ích cho logging/chẩn đoán, nhưng không phải định danh để `Class.forName` tải lại.
3. **Không coi hidden là biện pháp bảo mật.** Kiểm soát quyền bằng các cơ chế access/module/security thích hợp, không dựa trên việc lớp “khó tìm”.
4. **Cân nhắc vòng đời.** Giữ `Class`, instance hay handle có thể giữ hidden class sống; `STRONG` liên kết mạnh với loader. Không xây tính đúng đắn dựa trên thời điểm GC tự động dỡ lớp.
5. **Xác định giới hạn tooling.** Những công cụ bắt buộc có binary name hoặc trông chờ enumerate toàn bộ nest có thể không bao quát hidden classes; agent/JVMTI có các hạn chế riêng đối với biến đổi hidden class.

Một hidden class vẫn có thể kế thừa lớp thường hoặc triển khai interface phù hợp với bytecode; “hidden” không đồng nghĩa “không dùng được đa hình”. Tuy nhiên, việc mã khác viết một tham chiếu biểu tượng đến chính tên hidden class là điều không thể.

## 8. Những nhầm lẫn và lỗi thường gặp

| Nhầm lẫn / triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Thấy dấu `$` trong tên nên cho rằng lớp hidden | Lớp lồng thường có binary name chứa `$` | Kiểm tra `Class.isHidden()` |
| `Class.forName(hidden.getName())` báo không tìm thấy | Hidden class không có binary name để class loader khám phá | Giữ `Class<?>`/`Lookup`/factory khi tạo |
| `getNestMembers()` không có hidden class dù `isNestmateOf()` đúng | Hidden nestmates không được ghi trong `NestMembers` của host | Dùng `isNestmateOf()` để kiểm tra quan hệ; lưu danh sách lớp đã định nghĩa nếu cần duyệt |
| `defineHiddenClass` ném `IllegalAccessException` | Lookup không có quyền full privilege phù hợp | Gọi từ ngữ cảnh có quyền thực sự; không giả định mọi lookup đều định nghĩa được |
| `defineHiddenClass` thất bại vì package của bytecode | Bytecode phải cùng runtime package với lookup class | Tạo/đọc bytecode trong đúng package và dùng lookup hợp lệ |
| `ClassFormatError` hoặc lỗi xác minh bytecode | Dữ liệu class file không hợp lệ/không phù hợp | Biên dịch hoặc sinh bytecode chuẩn; kiểm tra class file trước khi định nghĩa |
| Gọi member `private` của host thất bại | Không có quan hệ nestmate/quyền cần thiết | Chỉ dùng `NESTMATE` nếu thực sự cần và đáp ứng điều kiện API |
| Tưởng `initialize=false` nghĩa là không bao giờ khởi tạo | Nó chỉ không yêu cầu khởi tạo tại thời điểm định nghĩa | Hiểu quy tắc khởi tạo JVM khi dùng lớp về sau |

## 9. Bài tập tự kiểm tra

**Bài 1 — Nhận diện:** Với `Outer.Inner.class` (static member class thông thường), so sánh `isHidden()`, `getName()` và `getCanonicalName()` với hidden class ở ví dụ. Giải thích tại sao tên của cả hai có thể chứa `$` nhưng chỉ một lớp là hidden.

**Bài 2 — Danh tính:** Gọi `defineHiddenClass(bytecode, true, NESTMATE)` **hai lần** với cùng bytecode. So sánh `Class<?>` của hai lần bằng `==` và thử gọi `Class.forName` bằng tên của từng hidden class. Dự đoán: hai lần tạo ra hai đối tượng `Class<?>` khác nhau, cả hai đều `isHidden()==true` và không thể tìm lại bằng `forName`.

**Bài 3 — Nest:** Bỏ `NESTMATE` khi định nghĩa lớp, quan sát `isNestmateOf(HiddenClassDemo.class)` và thử gọi `readHostSecret()`. Tự giải thích mối liên hệ giữa quyền truy cập `private` và quan hệ nest; phân biệt lỗi của bước này với lỗi tìm lớp bằng tên.

**Câu hỏi phỏng vấn:** “Nếu `Class.forName(hidden.getName())` không tìm được hidden class, tại sao `hidden.getDeclaredMethods()` vẫn hoạt động?” — Vì `forName` **tìm một `Class` từ binary name**, còn `getDeclaredMethods()` **truy vấn metadata của một đối tượng `Class` đã có sẵn**. Hai thao tác sử dụng đầu vào và cơ chế khác nhau.

## 10. Tài liệu gốc

- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): mục tiêu thiết kế, khả năng khám phá và vòng đời của hidden classes.
- [Java 17 — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isHidden()`, `getName()`, `getCanonicalName()`, `getNestHost()`, `isNestmateOf()`, `getNestMembers()`.
- [Java 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass(...)`, quyền lookup, quy tắc bytecode/runtime package.
- [Java 17 — `Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): `NESTMATE` và `STRONG`.
