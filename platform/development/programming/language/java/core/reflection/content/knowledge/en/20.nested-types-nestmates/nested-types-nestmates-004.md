# isMemberClass(), isLocalClass() và isAnonymousClass() trong Java Reflection

Trong Java, không phải mọi lớp đều được khai báo trực tiếp ở cấp tệp. Một lớp có thể là thành viên của một lớp khác, được khai báo bên trong một khối lệnh, hoặc được tạo bằng biểu thức lớp vô danh. Bộ ba phương thức `Class.isMemberClass()`, `Class.isLocalClass()` và `Class.isAnonymousClass()` giúp nhận diện **kiểu khai báo** của một `Class<?>` lúc chạy.

Mục tiêu của bài học: phân biệt chính xác ba loại lớp, dùng các phương thức Reflection để truy tìm ngữ cảnh bao quanh, và tránh suy luận sai từ tên lớp hoặc quan hệ nestmate.

## 1. Ba phương thức trả lời ba câu hỏi khác nhau

Cả ba đều là phương thức instance của `java.lang.Class`, không nhận đối số và trả về `boolean`:

```java
boolean member = type.isMemberClass();
boolean local = type.isLocalClass();
boolean anonymous = type.isAnonymousClass();
```

| Phương thức | Trả về `true` khi | Ví dụ điển hình |
| --- | --- | --- |
| `isMemberClass()` | Lớp được khai báo là **thành viên** trong phần thân một lớp hoặc kiểu bao ngoài | `Outer.StaticNested`, `Outer.Inner` |
| `isLocalClass()` | Lớp có tên được khai báo **cục bộ trong một khối**, chẳng hạn trong phương thức hoặc constructor | `class Local {}` bên trong `main` |
| `isAnonymousClass()` | Lớp được khai báo qua **biểu thức tạo lớp vô danh**, không có tên khai báo riêng | `new Runnable() { ... }` |

Đây là ba cách phân loại khác nhau và không chồng lên nhau đối với một lớp cụ thể. Nếu cả ba trả về `false`, **không đủ kết luận đó là lớp top-level**: đối tượng `Class` còn có thể đại diện cho primitive, mảng và nhiều kiểu khác.

### 1.1. Member class: lớp thành viên

```java
class Outer {
    static class StaticNested {}  // Member class, đồng thời là static nested class
    class Inner {}                // Member class, đồng thời là non-static inner class
}
```

Cả `Outer.StaticNested.class.isMemberClass()` lẫn `Outer.Inner.class.isMemberClass()` đều là `true`. Từ khóa `static` quyết định lớp lồng có cần tham chiếu đến thể hiện của `Outer` hay không; nó **không** quyết định giá trị của `isMemberClass()`.

Lưu ý thuật ngữ: mọi inner class là một nested class, nhưng static nested class không phải inner class theo nghĩa của Java Language Specification. Trong ví dụ trên, cả hai vẫn là member classes.

### 1.2. Local class: lớp cục bộ có tên

```java
void process() {
    class Result {
        String value() { return "OK"; }
    }
    Class<?> type = Result.class;
    System.out.println(type.isLocalClass()); // true
}
```

`Result` có tên trong mã nguồn và phạm vi nhìn thấy cục bộ trong khối chứa khai báo. Local class có thể xuất hiện trong phương thức, constructor hoặc khối khởi tạo; không nhất thiết phải được định nghĩa trong một phương thức instance. Phạm vi tên và khả năng bắt biến cục bộ của lớp này tuân theo các quy tắc của ngôn ngữ Java. Khi dùng biến cục bộ từ khối bao ngoài, biến đó phải là `final` hoặc *effectively final*.

Một local class **không trở thành member class** chỉ vì bytecode có tên chứa dấu `$` hoặc vì `getEnclosingClass()` trả về một lớp bao ngoài.

### 1.3. Anonymous class: lớp vô danh

```java
Runnable job = new Runnable() {
    @Override
    public void run() {
        System.out.println("Running");
    }
};
System.out.println(job.getClass().isAnonymousClass()); // true
```

Biểu thức `new Runnable() { ... }` khai báo và khởi tạo một lớp không có tên khai báo riêng. `job.getClass()` trỏ đến lớp vô danh do biểu thức đó tạo ra; nó không phải `Runnable.class`.

Đừng nhầm anonymous class với biểu thức lambda:

```java
Runnable lambda = () -> System.out.println("Running");
```

Lambda được triển khai theo cơ chế riêng của JVM; không dùng `isAnonymousClass()` để xác định một đối tượng có được tạo từ lambda hay không. Hình dạng lớp runtime của lambda là chi tiết triển khai, không phải hợp đồng nhận diện bằng ba phương thức này.

## 2. Ví dụ đầy đủ, chạy được trên Java 17+

Tạo tệp `ClassKindsDemo.java`:

```java
public class ClassKindsDemo {
    static class StaticMember {}
    class InnerMember {}

    public static void main(String[] args) {
        class Local {}

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {}
        };

        show("TopLevel", ClassKindsDemo.class);
        show("StaticMember", StaticMember.class);
        show("InnerMember", InnerMember.class);
        show("Local", Local.class);
        show("Anonymous", anonymous.getClass());

        System.out.println("Local declaring: " + Local.class.getDeclaringClass());
        System.out.println("Local enclosing class: " + Local.class.getEnclosingClass().getSimpleName());
        System.out.println("Local enclosing method: " + Local.class.getEnclosingMethod().getName());
        System.out.println("Anonymous simple name empty: " + anonymous.getClass().getSimpleName().isEmpty());
    }

    static void show(String label, Class<?> type) {
        System.out.println(label + " -> member=" + type.isMemberClass()
                + ", local=" + type.isLocalClass()
                + ", anonymous=" + type.isAnonymousClass());
    }
}
```

Biên dịch và chạy:

```bash
javac ClassKindsDemo.java
java ClassKindsDemo
```

Kết quả:

```text
TopLevel -> member=false, local=false, anonymous=false
StaticMember -> member=true, local=false, anonymous=false
InnerMember -> member=true, local=false, anonymous=false
Local -> member=false, local=true, anonymous=false
Anonymous -> member=false, local=false, anonymous=true
Local declaring: null
Local enclosing class: ClassKindsDemo
Local enclosing method: main
Anonymous simple name empty: true
```

Hai lớp `StaticMember` và `InnerMember` khác nhau ở ngữ nghĩa `static`/instance nhưng giống nhau về phân loại `member`. `Local` có tên riêng và được khai báo trong `main` nên `local=true`. Đối tượng `anonymous` có một lớp thực thi `Runnable` không được đặt tên trong mã nguồn nên `anonymous=true`.

Lưu ý rằng `ClassKindsDemo.class` đại diện cho lớp top-level của ví dụ. Ba kết quả `false` chỉ có ý nghĩa top-level trong bối cảnh ta **đã biết** đối tượng đó là lớp thường được khai báo ở cấp tệp.

## 3. Phân biệt declaring class và enclosing context

Để tìm hiểu một lớp nằm ở đâu trong mã nguồn, kết hợp bộ ba phân loại với các API khác của `Class<?>`:

| API | Ý nghĩa chính | Member class | Local class trong `main` | Anonymous class trong `main` |
| --- | --- | --- | --- | --- |
| `getDeclaringClass()` | Lớp trực tiếp khai báo kiểu **thành viên** | `Outer.class` | `null` | `null` |
| `getEnclosingClass()` | Lớp bao quanh khai báo | `Outer.class` | Lớp chứa `main` | Lớp chứa `main` |
| `getEnclosingMethod()` | Phương thức trực tiếp chứa khai báo, nếu có | Thường `null` | `main` | `main` |
| `getEnclosingConstructor()` | Constructor trực tiếp chứa khai báo, nếu có | Thường `null` | `null` trong ví dụ | `null` trong ví dụ |
| `getSimpleName()` | Tên đơn giản | Tên lớp thành viên | Tên lớp cục bộ | Chuỗi rỗng |
| `getCanonicalName()` | Tên chuẩn nếu có | Thường khác `null` | `null` | `null` |

Các cột cuối giả định chính ngữ cảnh khai báo của ví dụ ở mục 2. Với lớp cục bộ hay vô danh được khai báo trong constructor, `getEnclosingConstructor()` có thể trả về constructor đó. Nếu chúng được khai báo trong khối khởi tạo hoặc khởi tạo trường, `getEnclosingMethod()` và `getEnclosingConstructor()` có thể đều trả về `null` dù `getEnclosingClass()` không phải `null`.

Ví dụ đối chiếu:

```java
Class<?> member = ClassKindsDemo.StaticMember.class;
System.out.println(member.getDeclaringClass() == ClassKindsDemo.class); // true
System.out.println(member.getEnclosingMethod() == null);                 // true
```

Đây là đoạn minh họa bổ sung, có thể đặt trong `main` của ví dụ trước. Trong đó `getDeclaringClass()` trả về đối tượng `Class` đại diện cho lớp khai báo thành viên, còn `getEnclosingMethod()` trả về `null` bởi `StaticMember` không được khai báo bên trong một phương thức.

**Quy tắc sử dụng:** `getDeclaringClass()` hữu ích để tìm chủ thể khai báo một member class; `getEnclosingClass()` thích hợp hơn khi quan tâm đến lớp bao quanh của cả member, local và anonymous class.

## 4. Liên hệ với kiểu lồng và nestmate

Từ Java 11, khái niệm **nest** hỗ trợ các lớp thuộc cùng một nhóm truy cập thành viên private ở mức JVM. `Class` có các API như `getNestHost()`, `getNestMembers()` và `isNestmateOf(...)`.

Điểm cần phân biệt:

- `isMemberClass()`, `isLocalClass()`, `isAnonymousClass()` mô tả **hình thức khai báo** của chính lớp được phản chiếu.
- `getNestHost()` và `isNestmateOf(...)` mô tả **quan hệ nest** phục vụ quy tắc truy cập ở mức JVM.
- Một lớp local hoặc anonymous có thể thuộc cùng nest với lớp bao quanh mà vẫn có `isMemberClass() == false`. Vì thế không dùng quan hệ nestmate để suy ra member class.

Tương tự, tên nhị phân thường có dấu `$` cho nhiều loại lớp lồng, nhưng đây **không phải tiêu chí Reflection đáng tin** để phân biệt member, local và anonymous. Những thành phần số trong tên lớp được compiler sinh ra là chi tiết triển khai, không nên hard-code hoặc dùng làm hợp đồng API.

## 5. Áp dụng khi kiểm tra Class<?> động

Khi một framework hoặc công cụ nhận `Class<?>` từ bên ngoài, có thể phân nhánh theo loại khai báo:

```java
static String declaredKind(Class<?> type) {
    if (type.isAnonymousClass()) {
        return "anonymous class";
    }
    if (type.isLocalClass()) {
        return "local class";
    }
    if (type.isMemberClass()) {
        return "member class";
    }
    return "other";
}
```

Đây là một **phương thức trợ giúp**, không phải chương trình độc lập. Có thể đặt nó trong bất kỳ lớp Java thích hợp nào. Nhánh `other` được đặt cố ý để tránh mặc định mọi kiểu còn lại đều là top-level.

Các tình huống thực tế:

1. **Logging và diagnostics:** ghi loại khai báo bằng các cờ Reflection, thay vì trông chờ `getSimpleName()` luôn có giá trị (lớp vô danh có tên đơn giản rỗng).
2. **Công cụ quét metadata:** xử lý member classes theo quan hệ `getDeclaringClass()`; local/anonymous classes cần kiểm tra `getEnclosingClass()` hoặc ngữ cảnh phương thức/constructor.
3. **Sinh tài liệu hay tên hiển thị:** ưu tiên một nhãn có ý nghĩa do ứng dụng đặt nếu gặp anonymous class; tránh hiển thị trực tiếp tên nhị phân có số compiler sinh.

Nếu thực sự muốn kiểm tra một lớp có phải kiểu lồng hay không, hãy xác định rõ khái niệm cần dùng: **member**, **enclosed**, hay **nestmate**. Mỗi khái niệm cần API và điều kiện riêng.

## 6. Lỗi thường gặp và cách tự kiểm tra

- **Cho rằng static nested class không phải member class.** Sai: `static` không làm `isMemberClass()` thành `false`.
- **Đồng nhất local class và anonymous class.** Local class có tên khai báo (`class Local`); anonymous class dùng biểu thức tạo lớp không đặt tên (`new Interface() { ... }`).
- **Dùng `getDeclaringClass() == null` để khẳng định top-level.** Sai: local và anonymous class cũng thường trả về `null`.
- **Dựa vào `getName()` hoặc dấu `$` để phân loại.** Không cần thiết và dễ phụ thuộc compiler; hãy dùng trực tiếp ba phương thức `is...Class()`.
- **Xem lambda là anonymous class.** Không có bảo đảm đó; lambda và anonymous class khác nhau về ngữ nghĩa.
- **Coi ba cờ đều `false` là đủ để kết luận top-level.** Mảng và primitive cũng nằm ngoài ba loại; các `Class<?>` khác cũng có thể như vậy.

Tự kiểm tra: Với `new Thread() { }`, `isAnonymousClass()` của **đối tượng mới tạo** là gì? **`true`**. Với một lớp `static class Helper` nằm trong thân lớp khác, `isMemberClass()` là gì? **`true`**. Với `class Temp {}` được khai báo trong `main`, `getDeclaringClass()` thường là gì? **`null`**, còn `getEnclosingMethod()` là `main`.

Tài liệu tham khảo: [Javadoc `java.lang.Class` (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).