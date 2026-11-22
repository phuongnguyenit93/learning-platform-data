# Nestmate và quyền truy cập private giữa các lớp liên quan trong Java Reflection

## 1. Nestmate giải quyết vấn đề gì?

Từ **Java 11**, JVM hỗ trợ khái niệm **nest** (nhóm lớp cùng tổ): một *nest host* và các lớp thành viên (*nest members*) có quan hệ được ghi trong class file. Các lớp **nestmate** có thể truy cập trực tiếp thành viên `private` của nhau theo quy tắc kiểm tra quyền truy cập của JVM, miễn là cùng một nest hợp lệ.

Vấn đề gốc: trong Java, một lớp bên ngoài và những lớp lồng bên trong nó được phép sử dụng thành viên `private` của nhau ngay ở mức ngôn ngữ.

```java
class Library {
    private String code = "BOOK";

    static class Checker {
        String check(Library library) {
            return library.code; // Hợp lệ theo luật của Java
        }
    }
}
```

Trước Java 11, bytecode không biểu diễn được trực tiếp toàn bộ quyền riêng tư giữa các lớp này theo cơ chế truy cập `private` cũ. Trình biên dịch thường phải sinh các phương thức cầu nối `synthetic` dạng `access$...` để lớp lồng đọc thành viên `private` của lớp bao. Java 11 đưa ra **nest-based access control** (JEP 181): JVM hiểu quan hệ nest và có thể cho phép truy cập `private` trực tiếp mà không cần cầu nối đó.

> **Phân biệt quan trọng:** “Cùng nest” là quan hệ được JVM công nhận giữa các `Class`, không đơn thuần là “cùng package”, “cùng superclass”, “có tên lớp giống nhau” hoặc “đang được một framework load cùng lúc”.

## 2. Những lớp nào thuộc một nest?

Trong mã Java thông thường, các lớp lồng (*nested classes*), gồm `static nested class`, *inner class*, các lớp local/anonymous được biên dịch tương ứng, có thể cùng nest với lớp bao ngoài cùng. Những lớp lồng cấp sâu vẫn có cùng nest host ngoài cùng. Các lớp **top-level độc lập** dù nằm cùng file nguồn hoặc cùng package vẫn không tự trở thành nestmate.

```java
public class House {
    private int secret = 7;

    static class Room {
        private String note = "private-room";

        static class Box {
            private long id = 1;
        }
    }

    class Window {
        private boolean open;
    }
}
```

Trong cấu trúc này, các lớp `House`, `House.Room`, `House.Room.Box` và `House.Window` có thể thuộc cùng nest. Không có “nest con” tách riêng chỉ vì `Box` được khai báo sâu hơn.

**Nest host** là lớp đại diện cho tổ. Trong ví dụ trên, khi biên dịch Java 11+ theo cách thông thường, `House.class` là host; `House.Room.class.getNestHost()` và `House.Room.Box.class.getNestHost()` trả về `House.class`. Chính lớp host cũng là một thành viên của nest.

**Được phép truy cập `private`** là quyền giữa các nestmate, theo cả hai chiều:

- Lớp lồng có thể đọc field `private` hoặc gọi method `private` của lớp bao.
- Lớp bao có thể truy cập member `private` của lớp lồng.
- Hai lớp lồng là “anh em” cùng host có thể truy cập member `private` của nhau, khi có tham chiếu/phương thức phù hợp.

Sự tồn tại của quan hệ nest **không làm member trở thành `public`**, cũng không khiến tất cả lớp ở cùng package được truy cập.

## 3. Ba API Reflection nhận diện nestmate

Các phương thức của `java.lang.Class` có từ Java 11:

| API | Trả về | Cách hiểu |
| --- | --- | --- |
| `clazz.getNestHost()` | `Class<?>` | Lớp host của nest chứa `clazz`; với lớp không tham gia tổ nhiều lớp, thường là chính nó |
| `clazz.getNestMembers()` | `Class<?>[]` | Các lớp thành viên của nest, gồm cả host; không phụ thuộc thứ tự phần tử |
| `a.isNestmateOf(b)` | `boolean` | `true` nếu hai đối tượng `Class` được JVM xác định là thuộc cùng nest |

Ví dụ khi đã có các lớp trong mục 2:

```java
Class<?> host = House.Room.Box.class.getNestHost();
boolean related = House.Room.class.isNestmateOf(House.Window.class);
Class<?>[] members = House.class.getNestMembers();
```

Các dòng này là đoạn **minh họa nằm trong một phương thức Java**, không phải chương trình độc lập. `host` tương ứng `House.class` và `related` là `true` nếu ví dụ được biên dịch/chạy trên JVM hỗ trợ nestmate.

Lưu ý sử dụng:

1. Không dựa vào thứ tự phần tử từ `getNestMembers()`. Nếu cần hiển thị ổn định, lấy tên rồi sắp xếp.
2. `getNestMembers()` nói về nest, **không đồng nghĩa** với `getDeclaredClasses()`: phương thức sau dùng để lấy các lớp/interface là thành viên khai báo trực tiếp, không nhằm liệt kê đầy đủ mọi nestmate.
3. `isNestmateOf` là phép kiểm tra quan hệ giữa **class**, không phải một phép thử toàn bộ các rào cản khi truy cập một field/method cụ thể.
4. Đừng suy luận quan hệ nest bằng cách cắt chuỗi từ dấu `$` trong tên class; tên binary không đủ xác lập quyền truy cập.

## 4. Chương trình Java 17+: kiểm chứng private qua Reflection

Lưu toàn bộ nội dung bên dưới vào **`NestmateDemo.java`** (không tách các lớp ra tệp khác). `NestmateDemo` và hai lớp lồng `MemberReader`, `Peer` thuộc cùng nest; `Outside` là một lớp top-level độc lập, được đặt cùng tệp để chứng minh **cùng package và cùng source file vẫn không đủ**.

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;

public class NestmateDemo {
    private String secret = "ALPHA";

    private String combine(String suffix) {
        return secret + suffix;
    }

    private static class MemberReader {
        static void inspect(NestmateDemo obj) throws Exception {
            // Quyền private được cấp vì MemberReader và NestmateDemo cùng nest.
            System.out.println("direct: " + obj.secret);

            // getDeclared* chỉ tìm metadata, không tự tắt access check.
            Field field = NestmateDemo.class.getDeclaredField("secret");
            Method method = NestmateDemo.class.getDeclaredMethod(
                    "combine", String.class);

            // Không gọi setAccessible(true).
            System.out.println("field canAccess: " + field.canAccess(obj));
            System.out.println("field value: " + field.get(obj));
            System.out.println("method canAccess: " + method.canAccess(obj));
            System.out.println("method result: " + method.invoke(obj, "!"));
        }
    }

    private static class Peer {}

    public static void main(String[] args) throws Exception {
        System.out.println("same nest: "
                + MemberReader.class.isNestmateOf(Peer.class));
        System.out.println("outside nest: "
                + MemberReader.class.isNestmateOf(Outside.class));
        System.out.println("peer listed: "
                + Arrays.asList(NestmateDemo.class.getNestMembers())
                        .contains(Peer.class));

        NestmateDemo obj = new NestmateDemo();
        MemberReader.inspect(obj);
        Outside.inspect(obj);
    }
}

// Lớp top-level độc lập: không tự thuộc nest của NestmateDemo.
class Outside {
    static void inspect(NestmateDemo obj) throws Exception {
        Field field = NestmateDemo.class.getDeclaredField("secret");

        System.out.println("outside canAccess: "
                + field.canAccess(obj));
        try {
            field.get(obj);
        } catch (IllegalAccessException ex) {
            System.out.println("outside read: IllegalAccessException");
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17+**, với target mặc định của JDK hiện đại:

```bash
javac NestmateDemo.java
java NestmateDemo
```

Kết quả:

```text
same nest: true
outside nest: false
peer listed: true
direct: ALPHA
field canAccess: true
field value: ALPHA
method canAccess: true
method result: ALPHA!
outside canAccess: false
outside read: IllegalAccessException
```

### Phân tích từng nhóm kết quả

1. `MemberReader.class.isNestmateOf(Peer.class)` là `true` dù hai lớp lồng không nằm trong quan hệ kế thừa: cả hai có chung nest host.
2. `Outside.class` không thuộc nest chỉ vì cùng package/source file; `isNestmateOf` trả về `false`.
3. `getNestMembers()` của `NestmateDemo` chứa `Peer.class`. Không dùng vị trí trong mảng để khẳng định thành viên.
4. Dòng `direct: ALPHA` là truy cập `private` thông qua cú pháp Java thường. Hai dòng `canAccess` và hai kết quả Reflection cho thấy khi **caller là `MemberReader` cùng nest**, kiểm tra truy cập thông thường cũng cho phép Reflection đọc field và gọi method `private` **mà không dùng `setAccessible(true)`**.
5. `Outside` vẫn lấy được đối tượng `Field` bằng `getDeclaredField`: truy vấn metadata thành công nhưng `canAccess(obj)` là `false`. Khi dùng `Field.get`, JVM/Reflection ném `IllegalAccessException` vì caller không có quyền.
6. `Method.invoke` trong ví dụ trả về `ALPHA!`. Đây là lúc method được *gọi thực sự*, khác với việc chỉ tra cứu `Method` bằng `getDeclaredMethod`.

Chương trình cố ý dùng `throws Exception` ở ví dụ tập trung để dễ đọc. Trong ứng dụng, hãy xử lý các ngoại lệ Reflection đúng ngữ nghĩa: `NoSuchFieldException`, `NoSuchMethodException` cho tra cứu; `IllegalAccessException` cho truy cập; `InvocationTargetException` khi method đích ném lỗi; và các trường hợp không đúng kiểu/đối số.

## 5. Có quyền private qua nestmate khác gì setAccessible?

Có ba thao tác độc lập dễ bị nhầm:

**(1) Tìm metadata.** `getDeclaredField("secret")` và `getDeclaredMethod("combine", String.class)` trả về đối tượng mô tả thành viên, kể cả `private`. `getField`/`getMethod` dành cho tập member `public` theo quy tắc tra cứu tương ứng.

**(2) Kiểm tra quyền truy cập thông thường.** `field.canAccess(obj)` hoặc `method.canAccess(obj)` cho biết caller hiện tại có quyền thực hiện thao tác trên đối tượng cụ thể theo trạng thái truy cập Reflection hiện tại hay không. Caller của phép kiểm tra có ý nghĩa: trong ví dụ, chạy trong `MemberReader` trả `true`, còn chạy trong `Outside` trả `false` đối với field `private` đó. Đối số phải hợp lệ: với instance field/method, truyền đúng receiver; với static member, dùng `null`. Tham số sai có thể gây `IllegalArgumentException`.

**(3) Yêu cầu bỏ qua kiểm tra truy cập Java thông thường.** `setAccessible(true)` hoặc `trySetAccessible()` là thao tác riêng, chịu ràng buộc module của JPMS. Dùng chúng để bỏ qua access check không phải điều kiện tiên quyết khi caller có quyền truy cập nhờ quan hệ nest.

| Caller và hành động | Tìm metadata `private` bằng `getDeclared...` | Truy cập thực sự khi chưa bật accessible override |
| --- | --- | --- |
| Một lớp nestmate hợp lệ | Có | Có, nếu kiểu thành viên/receiver/điều kiện khác phù hợp |
| Lớp top-level cùng package nhưng ngoài nest | Có thể | Không có quyền `private` chỉ vì cùng package |
| Một subclass nhưng ngoài nest | Có thể | Kế thừa **không** cấp quyền `private` |
| Thư viện ngoài module | Có thể tra cứu metadata tùy API | Truy cập `private` không tự được cấp; `setAccessible` còn chịu quy tắc `opens` |

**JPMS:** Trên Java 9+, một framework có thể bị chặn khi cố gọi `setAccessible(true)` vào thành viên không public của package trong một module khác chưa `opens` package đó. `trySetAccessible()` có thể trả về `false`; `setAccessible(true)` có thể ném `InaccessibleObjectException`. Đừng mặc định thêm `--add-opens` hoặc bỏ qua lỗi. Thiết kế API public hoặc thiết lập `opens` có chủ đích khi framework thật sự cần deep reflection.

Bản thân nest hợp lệ không được trải tùy tiện giữa các module: các member phải thỏa điều kiện lớp/runtime package/class loader theo quy định JVM. Do đó không thể dùng nestmate để tự động vượt qua ranh giới bảo vệ của một module khác.

## 6. Cơ chế ở bytecode/JVM

### Java 8 và trước đó: compiler thường sinh accessor

Vì JVM cũ chỉ cho phép truy cập thành viên `private` bên trong **chính class sở hữu** (trong khi mã Java hỗ trợ truy cập qua lớp lồng), compiler phải phát sinh cầu nối `synthetic`, ví dụ tên dạng `access$000` hoặc tương tự. Lớp lồng gọi cầu nối thay cho truy cập `private` trực tiếp. Tên/cách sinh cầu nối là **chi tiết của compiler**, không phải API ổn định.

### Java 11+: thông tin nest trong class file

JEP 181 bổ sung thuộc tính class file:

- **`NestHost`:** class member chỉ ra host của mình.
- **`NestMembers`:** host liệt kê các class member cùng nest.

Khi thực hiện kiểm tra quyền truy cập `private`, JVM xét hai class có thuộc cùng nest **được xác minh hợp lệ** hay không. Việc chỉ ghi tên một lớp khác vào class file chưa đủ: JVM còn kiểm tra tính hợp lệ của quan hệ, gồm sự đồng ý từ host và các ràng buộc runtime package/class loader. Dữ liệu class file giả mạo hoặc không nhất quán có thể làm quá trình phân giải/kiểm tra thất bại; không nên tạo quan hệ nest bằng cách sửa tên class thủ công.

**Phiên bản biên dịch rất quan trọng.** Chạy chương trình trên JDK mới **không** tự biến bytecode target Java 8 thành bytecode nestmate: compiler tạo và ghi thông tin nest khi target/class-file version cho phép. Nếu cần hỗ trợ JVM cũ, chọn `--release` phù hợp và hiểu rằng compiler có thể dùng synthetic accessors. Java 8 không nhận diện các thuộc tính nest của class file Java 11.

Có thể kiểm tra class file **sau khi biên dịch**:

```bash
javap -v NestmateDemo
javap -v 'NestmateDemo$MemberReader'
```

Lệnh trên dùng cú pháp trích dẫn single quote phù hợp với shell Unix. Trong PowerShell cũng có thể đặt tên lớp chứa `$` trong single quotes. Hãy tìm thuộc tính `NestMembers` ở host và `NestHost` ở member. Kết quả của `javap -v` rất dài, khác nhau theo compiler/phiên bản và không được dùng như output cố định của bài.

Không nhầm nest metadata với `InnerClasses` hoặc `EnclosingMethod`: những thuộc tính này phục vụ thông tin cấu trúc lớp lồng/ngữ cảnh bao, nhưng không thay thế quy tắc kiểm tra nestmate của JVM.

## 7. Nestmate không đồng nghĩa với kế thừa, package hay lexical access ở mọi ngữ cảnh

### 7.1. Nestmate so với subclass

```java
class Parent {
    private int hidden = 5;
}

class Child extends Parent {
    // Không thể viết: int n = hidden;
}
```

`Child` không có quyền truy cập `private` của `Parent` chỉ vì `extends`. Một subclass bên ngoài nest cũng không thể gọi `getDeclaredField("hidden").get(instance)` mà tự nhiên được phép. Nếu một nested class đồng thời là subclass và nestmate thì quyền `private` bắt nguồn từ **nest**, không phải inheritance.

### 7.2. Cùng package hoặc cùng tệp .java

Hai top-level class cùng package có thể truy cập các thành viên package-private hợp lệ nhưng không được truy cập `private` của nhau. Lớp `Outside` trong chương trình trên cho thấy **cùng tệp nguồn cũng không tạo nest**. Không dùng `Class.getPackageName()` hay tên binary làm phép thử nestmate; dùng `isNestmateOf`.

### 7.3. Nested class không luôn là inner class

- `static nested class` không tự giữ tham chiếu đến instance của lớp ngoài. Nó vẫn có thể là nestmate và truy cập `private` của đối tượng ngoài nếu **đã có tham chiếu**.
- `inner class` (non-static) thường có ngữ cảnh đối tượng bao ngoài, nhưng việc có tham chiếu đó và việc được JVM cấp quyền `private` là hai vấn đề riêng.
- Nest membership không cấp quyền đọc field instance khi không có một receiver thích hợp; `private` access permission và sự tồn tại của đối tượng không phải một.

### 7.4. Reflection metadata và synthetic members

Reflection có thể quan sát những member `synthetic` do compiler sinh. Khi chạy mã biên dịch target cũ, có thể thấy các method `access$...`; khi dùng target Java 11+, chúng thường không còn cần thiết cho truy cập xuyên các nestmate. Đừng dựa vào số lượng hoặc tên synthetic members để kết luận rằng ứng dụng hoạt động giống nhau giữa các compiler.

Các công cụ introspection có thể dùng `Method.isSynthetic()`, `Field.isSynthetic()` và `Method.isBridge()` để phân tích chi tiết. Chỉ lọc chúng nếu quy tắc nghiệp vụ cho phép; đối với chẩn đoán bytecode, thông tin synthetic có thể rất quan trọng.

## 8. Lưu ý khi dùng Reflection và xử lý lỗi

1. **Không dùng `getFields()` để tìm field `private`.** Cần `getDeclaredField()`; phương thức đó tìm metadata được khai báo ngay trong class, không tự đi qua superclass.
2. **Không đồng nhất “tìm thấy” với “được phép dùng”.** `getDeclaredMethod()` tìm metadata, `canAccess()` kiểm tra quyền với caller và receiver hiện tại, `invoke()` mới thực thi. Đừng bỏ qua kiểm tra ngoại lệ.
3. **Không kiểm tra quyền từ sai vị trí.** Kết quả `canAccess` có thể khác giữa code trong nestmate và framework ngoài nest; gọi phép kiểm tra ở nơi khác có thể cho kết luận khác.
4. **Không cố truy cập sâu chỉ vì quan hệ source code.** Chỉ các quan hệ nest hợp lệ ở runtime mới hỗ trợ quyền đặc biệt. Các class loader/module, target bytecode và công cụ instrument bytecode có thể ảnh hưởng đến metadata thực tế.
5. **Không dùng quan hệ nest để vượt JPMS.** `setAccessible` vẫn theo module boundary/`opens` và phải được xem xét riêng.
6. **Không giả định mọi field/method đều là instance member.** `canAccess(null)` thích hợp cho static member, còn instance member cần receiver đúng kiểu.
7. **Không so sánh thứ tự từ `getNestMembers()`.** Nếu hiển thị tài liệu, sắp xếp theo tên; nếu kiểm tra sự hiện diện, dùng `contains` hoặc so sánh đối tượng `Class`.
8. **Không dùng `getNestMembers()` thay cho phân tích mọi lớp có quan hệ kế thừa.** Nest mô tả quyền riêng tư giữa các lớp cùng tổ, không mô tả toàn bộ type hierarchy.

Khi thiết kế framework, bước thực tế thường là: xác định `Class<?>` chủ sở hữu, đọc member qua `getDeclared...`, kiểm tra cần metadata hay cần thực thi, xét quyền truy cập tại điểm thực thi, và chỉ cân nhắc `trySetAccessible()` khi thực sự phải gọi private từ ngoài nest và cấu hình module cho phép.

## 9. Tự kiểm tra và thực hành

**Câu 1.** Vì sao `MemberReader` đọc được `secret` trực tiếp, trong khi `Outside` không thể?
**Đáp án:** `MemberReader` thuộc cùng nest với `NestmateDemo`; `Outside` là top-level class độc lập ngoài nest. Cùng tệp nguồn không tạo quyền `private`.

**Câu 2.** `getDeclaredField("secret")` trong `Outside` có trả về `Field` không? Vì sao đọc field vẫn thất bại?
**Đáp án:** Có, vì tra cứu metadata là bước khác kiểm tra quyền; `Field.get` áp dụng quyền truy cập từ caller ngoài nest và ném `IllegalAccessException`.

**Câu 3.** Có phải mọi subclass đều là nestmate của superclass?
**Đáp án:** Không. Kế thừa và nest là hai quan hệ độc lập.

**Câu 4.** Cách kiểm tra hai class có cùng nest là gì?
**Đáp án:** `A.class.isNestmateOf(B.class)`. Dùng `getNestHost()` để biết host; `getNestMembers()` để xem các member.

**Câu 5.** Vì sao không thể nhìn thấy `NestHost`/`NestMembers` khi biên dịch class theo target Java 8?
**Đáp án:** Cơ chế nestmate nằm trong class file Java 11+, còn target Java 8 dùng cơ chế tương thích cũ khi cần truy cập private giữa lớp lồng.

**Bài thực hành:** Thêm một field `private int value = 42;` vào `Peer` và một phương thức `private static int read(Peer peer)` vào `MemberReader` để truy cập `peer.value`. Kiểm tra có thể gọi từ `main` và so sánh với việc gọi qua Reflection từ `Outside`. Chỉ sử dụng quyền nestmate, không thêm `setAccessible(true)`; giải thích kết quả dựa trên caller, host và quyền `private`.

**Điểm cốt lõi:** Nestmate là quy tắc truy cập `private` ở cấp JVM được hỗ trợ từ Java 11. Reflection giúp **quan sát nest** (`getNestHost`, `getNestMembers`, `isNestmateOf`), **tìm metadata** (`getDeclared...`) và **thực hiện thao tác** (`get`/`invoke`). Ba việc đó có ý nghĩa khác nhau, vì thế hãy kiểm tra đúng quan hệ nest và quyền tại điểm sử dụng member.
