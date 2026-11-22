# Trường hợp tên chuẩn không tồn tại trong Java Reflection

## 1. Vấn đề cần hiểu

Khi phân tích một kiểu bằng Java Reflection, lời gọi `Class<?>.getCanonicalName()` **có thể trả về `null`**. Đây là kết quả hợp lệ của API: kiểu đó không có *canonical name* (tên chuẩn) theo Java Language Specification (JLS), không có nghĩa là `Class` bị lỗi, kiểu không tồn tại, hay Reflection không tìm thấy kiểu.

Tên chuẩn là tên ổn định theo quy tắc khai báo kiểu trong ngôn ngữ Java. Ví dụ, `java.lang.String`, `java.util.Map.Entry` và `java.lang.String[][]` là các tên chuẩn. Với kiểu thành viên, tên chuẩn dùng dấu chấm giữa tên kiểu bao ngoài và kiểu thành viên; nó khác với *binary name* thường dùng dấu `$`.

Các trường hợp tiêu biểu **không có tên chuẩn**:

- **Local class**: lớp khai báo bên trong khối lệnh như phương thức hoặc constructor.
- **Anonymous class**: lớp vô danh được tạo bằng biểu thức `new Interface() { ... }` hoặc `new Parent() { ... }`.
- **Hidden class**: lớp ẩn do API JVM tạo ra (có từ Java 15), thường phục vụ cơ chế runtime/framework.
- **Mảng có kiểu thành phần không có tên chuẩn**: ví dụ `Local[]` hoặc mảng của một anonymous class. Tính chất này lan truyền qua nhiều chiều mảng.
- Theo quy tắc tên chuẩn của JLS, **kiểu thành viên có kiểu bao ngoài không có tên chuẩn** cũng không có tên chuẩn.

Đây là danh sách các trường hợp quan trọng, không nên suy diễn rằng mọi kiểu do trình biên dịch sinh ra đều có cùng hành vi. Khi dùng một phiên bản Java mới, đối chiếu Javadoc của phiên bản đó.

## 2. Phân biệt bốn phương thức lấy tên

| API | Ý nghĩa chính | Khi kiểu không có tên chuẩn |
| --- | --- | --- |
| `getCanonicalName()` | Tên chuẩn theo JLS, hoặc `null` | Trả `null` |
| `getName()` | Tên do VM/JVM biểu diễn cho `Class`; với kiểu tham chiếu thông thường thường là binary name; với mảng dùng dạng mô tả riêng | Thường vẫn trả một chuỗi; không được đồng nhất với canonical name |
| `getSimpleName()` | Tên ngắn trong khai báo nguồn; anonymous class có tên ngắn rỗng | Local class thường có tên ngắn; anonymous class trả `""` |
| `getTypeName()` | Chuỗi cung cấp thông tin để hiển thị kiểu | Có thể dùng để ghi log nhưng không đảm bảo là tên chuẩn hay tên có thể nạp bằng `Class.forName` |

Ví dụ với lớp thành viên `CanonicalNameCases.Member`:

- `Member.class.getCanonicalName()` → `"CanonicalNameCases.Member"`.
- `Member.class.getName()` → `"CanonicalNameCases$Member"`.

Với `String[].class`, `getCanonicalName()` là `"java.lang.String[]"` còn `getName()` là `"[Ljava.lang.String;"`. Các chuỗi này phục vụ những mục đích khác nhau.

**Không thể** suy ra rằng `getCanonicalName() == null` kéo theo `getSimpleName() == null`: anonymous class có simple name là chuỗi rỗng, trong khi local class vẫn có simple name.

## 3. Ví dụ Java 17+: local, anonymous và mảng

Tạo tệp **`CanonicalNameCases.java`** với toàn bộ mã sau (không khai báo `package` để kết quả tên lớp dễ đối chiếu):

```java
import java.lang.reflect.Array;

public class CanonicalNameCases {
    static class Member {}

    private static void print(String label, Class<?> type) {
        System.out.println(label
                + " => canonical=" + type.getCanonicalName()
                + ", simple='" + type.getSimpleName() + "'"
                + ", local=" + type.isLocalClass()
                + ", anonymous=" + type.isAnonymousClass());
    }

    public static void main(String[] args) {
        class Local {}

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {}
        };

        Class<?> localArray =
                Array.newInstance(Local.class, 0).getClass();
        Class<?> anonymousArray =
                Array.newInstance(anonymous.getClass(), 0).getClass();

        print("Member", Member.class);
        print("Local", Local.class);
        print("Anonymous", anonymous.getClass());
        print("Local[]", localArray);
        print("Anonymous[]", anonymousArray);
        print("String[]", String[].class);
        print("int", int.class);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac CanonicalNameCases.java
java CanonicalNameCases
```

Kết quả chuẩn:

```text
Member => canonical=CanonicalNameCases.Member, simple='Member', local=false, anonymous=false
Local => canonical=null, simple='Local', local=true, anonymous=false
Anonymous => canonical=null, simple='', local=false, anonymous=true
Local[] => canonical=null, simple='Local[]', local=false, anonymous=false
Anonymous[] => canonical=null, simple='[]', local=false, anonymous=false
String[] => canonical=java.lang.String[], simple='String[]', local=false, anonymous=false
int => canonical=int, simple='int', local=false, anonymous=false
```

**Giải thích từng nhóm:**

1. `Member` là lớp thành viên có tên, được khai báo trong lớp `CanonicalNameCases`. Kiểu bao ngoài có tên chuẩn nên `Member` cũng có: `CanonicalNameCases.Member`. Không phải mọi nested class đều thiếu tên chuẩn.
2. `Local` được khai báo *bên trong phương thức `main`*, vì vậy `Local.class.getCanonicalName()` trả `null` mặc dù `getSimpleName()` trả `"Local"`. Tên VM (từ `getName()`) có thể chứa dấu `$` và số do compiler tạo; không nên mã hóa các giá trị này.
3. Đối tượng `anonymous` thuộc anonymous class. Nó không có tên định danh khai báo trong nguồn, nên cả tên chuẩn không tồn tại và tên ngắn là chuỗi rỗng.
4. `localArray` và `anonymousArray` đều là **Class biểu diễn kiểu mảng**, nên `isLocalClass()` và `isAnonymousClass()` của *bản thân mảng* đều `false`. Tuy vậy, `getCanonicalName()` của mảng vẫn `null` do **kiểu thành phần** không có tên chuẩn. Nếu tạo mảng hai chiều từ các kiểu này, kết quả vẫn `null`.
5. `String[]` có tên chuẩn hợp lệ vì `String` có tên chuẩn. Kiểu nguyên thủy `int` cũng có tên chuẩn là `"int"`. `void.class.getCanonicalName()` trả `"void"`.

Việc sử dụng `Array.newInstance(componentType, 0)` giúp lấy `Class` của mảng khi chỉ có `Class<?>` của kiểu thành phần lúc runtime.

## 4. Lý do tên chuẩn biến mất

### Local class

```java
void process() {
    class Worker {}
    Class<?> type = Worker.class;
    System.out.println(type.getCanonicalName()); // null
}
```

Đây là **mảnh mã minh họa bên trong một class**, không phải chương trình độc lập. `Worker` chỉ có phạm vi định danh trong ngữ cảnh cục bộ; không thể hình thành tên chuẩn theo quy tắc dành cho top-level/member types. Điều này không ngăn việc lấy `Class`, đọc phương thức/trường, hoặc khởi tạo theo các quyền truy cập phù hợp.

### Anonymous class

```java
Runnable task = new Runnable() {
    @Override public void run() {}
};
Class<?> type = task.getClass();
System.out.println(type.getCanonicalName()); // null
System.out.println(type.getSimpleName().isEmpty()); // true
```

Mã này cũng là **mảnh minh họa đặt trong phương thức**. Tên như `Outer$1` mà đôi khi thấy ở `getName()` là chi tiết định danh do runtime/compiler tạo, không biến anonymous class thành kiểu có canonical name.

### Hidden class

Java 15 bổ sung hidden classes, thường được định nghĩa bằng `MethodHandles.Lookup#defineHiddenClass`. Một `Class<?>` biểu diễn hidden class đáp ứng `isHidden() == true` và `getCanonicalName() == null`. Hidden class **không đồng nghĩa** với anonymous class: `isHidden()` và `isAnonymousClass()` kiểm tra hai đặc tính khác nhau. Mặc dù `getName()` có thể trả tên ở dạng nội bộ (chẳng hạn chứa `/`), không nên dùng chuỗi đó như tên nguồn Java hoặc dựa vào `Class.forName` để nạp hidden class.

### Hiệu ứng lan truyền qua kiểu chứa/mảng

Nếu kiểu gốc không có tên chuẩn, việc bọc kiểu đó thành `T[]` hay `T[][]` không tự tạo ra canonical name. Tương tự, một kiểu thành viên khai báo trong kiểu bao ngoài không có tên chuẩn không thể có tên chuẩn đầy đủ từ chuỗi các kiểu bao ngoài.

Ngược lại, các kiểu khai báo có tên như top-level class, member class, interface, enum, record (Java 16+) và array của các kiểu có tên chuẩn thường có `getCanonicalName()` khác `null`. **Nested/member không có nghĩa là local/anonymous.**

## 5. Xử lý an toàn trong code Reflection

### Khi chỉ cần tên để hiển thị hoặc ghi log

```java
static String displayName(Class<?> type) {
    String canonical = type.getCanonicalName();
    return canonical != null ? canonical : type.getTypeName();
}
```

Đây là **mảnh phương thức** cần đặt trong một class. `getTypeName()` là lựa chọn dự phòng để hiển thị, không phải lời hứa trả về tên chuẩn hoặc đầu vào hợp lệ cho `Class.forName`.

Tránh mẫu dễ gây `NullPointerException`:

```java
// Sai: getCanonicalName() có thể trả null.
String shortLabel = someClass.getCanonicalName().toLowerCase();
```

Thay vào đó, kiểm tra `null` và quyết định rõ chính sách: hiển thị tên thay thế, dùng định danh runtime, hoặc từ chối các kiểu không có tên chuẩn.

### Khi cần biết chính xác vì sao `null`

```java
import java.lang.reflect.Array;

static String explain(Class<?> type) {
    Class<?> elementType = type;
    while (elementType.isArray()) {
        elementType = elementType.getComponentType();
    }

    if (elementType.isHidden()) return "hidden class";
    if (elementType.isAnonymousClass()) return "anonymous class";
    if (elementType.isLocalClass()) return "local class";
    if (type.getCanonicalName() == null) {
        return "không có canonical name (trường hợp khác)";
    }
    return "có canonical name";
}
```

Đây là **mảnh phương thức cần đặt trong class**; dòng `import` nằm ở đầu tệp nguồn. `getComponentType()` gỡ từng lớp mảng để kiểm tra **kiểu phần tử cuối cùng**. Ví dụ, `Local[][]` có `isLocalClass() == false` ở cấp mảng, nhưng lớp `Local` bên trong là local class. Nhánh cuối dành cho các trường hợp khác mà API/JDK hiện tại hoặc tương lai có thể hỗ trợ; không nên tự kết luận tất cả giá trị `null` đều chỉ có một nguyên nhân.

Nếu chương trình cần nạp lại class theo tên, trước tiên xác định loại tên API yêu cầu. `Class.forName` sử dụng binary name cho lớp thông thường (ví dụ `"CanonicalNameCases$Member"`), không sử dụng canonical name `"CanonicalNameCases.Member"` của lớp thành viên. Local/anonymous/hidden classes không có một canonical name để lưu trữ rồi nạp lại theo cách này. Với reflection ở runtime, nên giữ chính `Class<?>`, đối tượng hoặc metadata được cấp trực tiếp thay vì đoán tên do compiler sinh ra.

## 6. Sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Mọi `Class<?>` đều có `getCanonicalName()`.” | API có quyền trả `null` cho kiểu không có tên chuẩn. |
| “Tên chuẩn `null` nghĩa là lớp không tồn tại.” | Kiểu vẫn có thể được tải, kiểm tra và sử dụng bằng Reflection. |
| “`getName()` và `getCanonicalName()` tương đương.” | Member types và arrays cho thấy hai cách đặt tên khác nhau; `getName()` không thay được quy tắc canonical name. |
| “Anonymous class cũng có tên ngắn `null`.” | `getSimpleName()` trả chuỗi rỗng `""`. |
| “`isLocalClass()` đủ để nhận diện mảng local class.” | `isLocalClass()` của chính kiểu mảng là `false`; phải đi qua `getComponentType()`. |
| “Lambda luôn là anonymous class.” | Lambda không được đồng nhất với anonymous class; lớp triển khai do runtime tạo là chi tiết hiện thực, không nên phụ thuộc vào tên hoặc cách phân loại của nó. |
| “Có thể lưu canonical name rồi dùng `Class.forName` cho mọi kiểu.” | Canonical name có thể `null`; ngay cả nested member types có tên chuẩn cũng thường cần binary name để dùng với `Class.forName`. |

## 7. Bài tập tự kiểm tra

1. Đặt `class Temp {}` trong phương thức, rồi so sánh `Temp.class.getCanonicalName()` và `Temp.class.getSimpleName()`. Giải thích vì sao một bên là `null` còn bên kia là `"Temp"`.
2. Với `Runnable` tạo bằng anonymous class, dự đoán kết quả của `getCanonicalName()`, `getSimpleName()` và `isAnonymousClass()`.
3. Tạo kiểu mảng hai chiều từ `Temp.class` bằng `Array.newInstance(Temp.class, 2, 3).getClass()`. Kiểm tra tên chuẩn của mảng, rồi gỡ từng `getComponentType()` để thấy kiểu gốc.
4. Thử `Member.class.getName()`, `Member.class.getCanonicalName()` và `Class.forName(Member.class.getName())`. Phân tích vì sao định danh dùng để nạp lớp và tên chuẩn khác nhau.

**Tự đánh giá:** Nếu biết `getCanonicalName() == null`, bạn đã biết tên chuẩn *không tồn tại*, nhưng chưa đủ dữ liệu để khẳng định nguyên nhân. Hãy phân loại kiểu qua `isArray()`/`getComponentType()`, `isLocalClass()`, `isAnonymousClass()`, `isHidden()` và ngữ cảnh tạo kiểu trước khi quyết định cách xử lý.

## 8. Tham khảo chính thức

- [Javadoc `Class.getCanonicalName()`, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getCanonicalName()) — điều kiện trả `null` và cách phân biệt tên.
- [Java Language Specification, mục 6.7](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.7) — quy tắc fully qualified names và canonical names.
- [Dev.java — Reading Class Names](https://dev.java/learn/reflection/names/) — ví dụ `getName()`, `getSimpleName()`, `getCanonicalName()`.