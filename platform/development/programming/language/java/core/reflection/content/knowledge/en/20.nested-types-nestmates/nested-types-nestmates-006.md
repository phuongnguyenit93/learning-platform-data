# getNestHost, getNestMembers và isNestmateOf trong Java Reflection

## 1. Nest và nestmate là gì?

Từ Java 11, JVM hỗ trợ **nest-based access control**: một nhóm class/interface cùng *nest* có thể truy cập trực tiếp các thành viên `private` của nhau khi quy tắc truy cập Java cho phép. Trong nhóm này:

- **Nest host** là class/interface chủ của nest.
- **Nest members** gồm host và các class/interface được JVM xác nhận thuộc nest ấy.
- Hai kiểu là **nestmates** nếu chúng có cùng nest host.

Khi biên dịch mã Java thông thường, compiler thường chọn class ngoài cùng (*top-level class*) làm host; các class/interface lồng trong nó, kể cả nhiều tầng, được ghi nhận là thành viên. Đây là khái niệm ở **mức class file và JVM**, không đơn thuần là quan hệ thụt lề hoặc từ khóa `static` trong mã nguồn.

Ví dụ cấu trúc:

```text
Outer                         ← nest host
├── Outer$Inner               ← member
├── Outer$Inner$Deep          ← member, host vẫn là Outer
└── Outer$Helper              ← member

AnotherTopLevel              ← nest khác, dù ở cùng package
```

Mỗi class/interface thuộc đúng một nest. Một class độc lập thường là host của **nest chỉ có chính nó**. Các API trong bài nằm trên `java.lang.Class` và có từ **Java 11**.

### Nest tồn tại để làm gì?

Trước Java 11, compiler đôi khi cần sinh phương thức cầu nối tổng hợp (*synthetic accessor*) để bytecode của lớp lồng truy cập `private` của lớp bao ngoài. Từ Java 11, JVM nhận biết quan hệ nest và cho phép truy cập `private` giữa những kiểu thật sự là nestmates, giảm nhu cầu sinh accessor kiểu đó. Cơ chế này vẫn tuân theo kiểm tra truy cập của JVM; nó không khiến mọi class trong cùng package hoặc cùng tên ngoài trở thành nestmate.

Trong class file, thông tin thường được biểu diễn bởi:

- `NestMembers`: đặt trên host, khai báo các ứng viên thành viên được host cho phép.
- `NestHost`: đặt trên member, trỏ về host.

JVM kiểm tra sự phù hợp của thông tin này, bao gồm việc các kiểu thuộc cùng *runtime package* (tên package **và** class loader định nghĩa phù hợp) và host xác nhận member. Chỉ khai báo một chiều hoặc chỉ có cùng package là chưa đủ.

## 2. So sánh nhanh ba phương thức

| Phương thức | Kiểu trả về | Câu hỏi nó trả lời | Điểm cần nhớ |
|---|---|---|---|
| `Class<?> getNestHost()` | `Class<?>` | Kiểu này thuộc nest có host là ai? | Host của chính nó thì trả về chính `Class` ấy. |
| `Class<?>[] getNestMembers()` | Mảng `Class<?>` | JVM xác nhận những kiểu nào cùng nest? | Phần tử đầu là host; các phần tử sau không có thứ tự được bảo đảm. |
| `boolean isNestmateOf(Class<?> c)` | `boolean` | Kiểu hiện tại và `c` có cùng host không? | So sánh quan hệ nest giữa **hai kiểu**; tham số `null` gây `NullPointerException`. |

Cả ba là **instance method của đối tượng `Class`**; ví dụ `Reader.class.getNestHost()`. Chúng trả về metadata của kiểu tại runtime, không phải instance của kiểu đó.

## 3. `getNestHost()`: xác định nest host

Chữ ký:

```java
public Class<?> getNestHost()
```

- Nếu gọi trên member lồng thông thường, kết quả là class ngoài cùng làm host.
- Nếu gọi trên host, kết quả chính là host.
- Class/interface độc lập thông thường có nest chỉ gồm chính nó nên kết quả cũng là chính nó.
- Với `int.class`, `void.class` và các array class như `String[].class`, API trả về chính đối tượng `Class` được gọi. Mỗi kiểu như vậy được xem là nest một phần tử.

Ví dụ ngắn:

```java
class Box {
    static class Inner {}
}

class Check {
    public static void main(String[] args) {
        System.out.println(Box.Inner.class.getNestHost() == Box.class);
        System.out.println(Box.class.getNestHost() == Box.class);
        System.out.println(int[].class.getNestHost() == int[].class);
    }
}
```

Lưu thành `Check.java` (chỉ `Check` có `main`), chạy `javac Check.java` rồi `java Check`, kết quả:

```text
true
true
true
```

Kết quả host **không nhất thiết là** `getDeclaringClass()` hoặc `getEnclosingClass()`. Chẳng hạn `Outer.Inner.Deep.class.getDeclaringClass()` trả về `Outer.Inner.class`, nhưng host thường là `Outer.class`.

## 4. `getNestMembers()`: liệt kê các kiểu cùng nest

Chữ ký:

```java
public Class<?>[] getNestMembers()
```

Phương thức trước tiên xác định host `H`, rồi trả về mảng có `H` ở **vị trí 0** và các thành viên được `H` ghi nhận mà JVM xác minh được. Gọi phương thức từ host hoặc từ member cùng nest đều nhằm mô tả nest ấy.

Những chi tiết dễ bị bỏ sót:

1. `result[0]` là host, nhưng **thứ tự những phần tử còn lại không được bảo đảm**. API còn cho phép phần tử trùng lặp; đừng dùng vị trí hoặc số lượng như một giao ước ứng dụng.
2. Không phải mọi tên ghi trong metadata nhất thiết xuất hiện trong kết quả. JVM cố nạp/xác minh từng ứng viên và chỉ đưa vào những kiểu được xác nhận thuộc nest.
3. Nếu kiểu có nest một phần tử, mảng chỉ chứa chính kiểu đó. Với primitive, array và `void` cũng vậy.
4. **Hidden classes** được thêm vào nest bằng `MethodHandles.Lookup.defineHiddenClass` không xuất hiện trong mảng chỉ dựa trên `NestMembers`. Vì thế `getNestMembers()` không phải API liệt kê tuyệt đối mọi lớp động ở runtime.
5. Để hiển thị hoặc so sánh danh sách, nên dùng tên lớp, sắp xếp hoặc tập hợp khi phù hợp, thay vì phụ thuộc vào thứ tự gốc của mảng.

`getNestMembers()` khác `getDeclaredClasses()`. Phương thức thứ hai mô tả các member class/interface khai báo **trực tiếp** trong một class và không phải là phép liệt kê toàn bộ nest. Nest có thể chứa lớp lồng nhiều tầng, local class hoặc anonymous class do compiler đưa vào.

## 5. `isNestmateOf(Class<?> c)`: kiểm tra quan hệ giữa hai kiểu

Chữ ký:

```java
public boolean isNestmateOf(Class<?> c)
```

Kết quả là `true` nếu hai kiểu cùng nest host; nếu không thì `false`.

- Member với member cùng host: `true`.
- Host với member của nó: `true`.
- Một kiểu với chính nó: `true`.
- Hai top-level class khác nhau trong cùng package: thông thường `false` vì mỗi class có host riêng.
- Hai kiểu chỉ có quan hệ kế thừa cha–con: **không mặc nhiên** là nestmates.
- Gọi `SomeClass.class.isNestmateOf(null)` ném `NullPointerException`.

Điều kiện về nest được quyết định bởi metadata/JVM, không bằng phép so sánh `getSimpleName()`, vị trí trong package hoặc chuỗi chứa ký tự `$` của tên class.

## 6. Ví dụ tổng hợp chạy được trên Java 17+

Tạo file **`NestDemo.java`** với nội dung:

```java
import java.util.Arrays;

public class NestDemo {
    private static final String KEY = "host secret";

    static class Reader {
        String read() {
            return KEY; // Reader truy cập private của host
        }
    }

    static class Writer {
        private String key = "writer secret";
    }

    public static void main(String[] args) {
        Class<?> host = NestDemo.class;
        Class<?> reader = Reader.class;
        Class<?> writer = Writer.class;

        System.out.println("Host of Reader: "
                + reader.getNestHost().getSimpleName());
        System.out.println("Reader vs Writer: "
                + reader.isNestmateOf(writer));
        System.out.println("Host vs Reader: "
                + host.isNestmateOf(reader));
        System.out.println("Reader vs Unrelated: "
                + reader.isNestmateOf(Unrelated.class));
        System.out.println("Reader vs String: "
                + reader.isNestmateOf(String.class));
        System.out.println("Reader reads host private: "
                + new Reader().read());
        System.out.println("Host reads Writer private: "
                + new Writer().key);

        System.out.println("All declared nest members:");
        Arrays.stream(host.getNestMembers())
                .map(Class::getName)
                .sorted()
                .forEach(name -> System.out.println("- " + name));
    }
}

// Cùng file và cùng package, nhưng là top-level class khác.
class Unrelated {}
```

Biên dịch và chạy:

```bash
javac --release 17 NestDemo.java
java NestDemo
```

Kết quả:

```text
Host of Reader: NestDemo
Reader vs Writer: true
Host vs Reader: true
Reader vs Unrelated: false
Reader vs String: false
Reader reads host private: host secret
Host reads Writer private: writer secret
All declared nest members:
- NestDemo
- NestDemo$Reader
- NestDemo$Writer
```

**Giải thích kết quả:**

- `Reader` và `Writer` là hai member class của `NestDemo`, có chung nest host `NestDemo`; vì vậy `isNestmateOf` trả về `true`.
- `Reader.read()` truy cập trường `private static KEY` của host. Ngược lại, phương thức `main` trên host đọc trường `private key` của `Writer`; cả hai truy cập đều hợp lệ.
- `Unrelated` là một top-level class riêng. Việc nó được khai báo trong **cùng file `.java` và cùng package** không làm nó thuộc nest của `NestDemo`.
- `String` thuộc nest khác, nên kiểm tra cũng trả về `false`.
- Danh sách được sắp theo tên bằng `sorted()` để kết quả minh họa cố định. `getNestMembers()` **không tự bảo đảm** thứ tự sau host.
- Mỗi kiểu `NestDemo`, `Reader`, `Writer` là một `Class<?>` riêng, nhưng đều báo cùng host.

Để quan sát class file, chạy:

```bash
javap -v NestDemo
javap -v 'NestDemo$Reader'
```

Trong kết quả `javap`, tìm `NestMembers` trên `NestDemo` và `NestHost` trên `NestDemo$Reader`. Trên Windows PowerShell, giữ dấu nháy đơn quanh tên có `$` để shell không diễn giải thành biến. Đây là bằng chứng ở bytecode cho quan hệ nest; nội dung đầy đủ của `javap` phụ thuộc phiên bản compiler.

## 7. Nest so với cấu trúc lồng trong mã nguồn

Ba API dễ bị nhầm lẫn:

| API | Ý nghĩa |
|---|---|
| `getNestHost()` | Host theo quy tắc nest của JVM. |
| `getDeclaringClass()` | Kiểu trực tiếp **khai báo** một member class/interface; `null` với kiểu không phải member class. |
| `getEnclosingClass()` | Kiểu bao quanh về mặt ngữ cảnh khai báo, hữu ích cả với local/anonymous class. |
| `getDeclaredClasses()` | Những member class/interface khai báo trực tiếp bên trong kiểu đang xét. |

Với cấu trúc:

```java
class Outer {
    static class Inner {
        static class Deep {}
    }
}
```

Các biểu thức sau đúng khi biên dịch thông thường trên Java 17:

```java
Outer.Inner.Deep.class.getDeclaringClass() == Outer.Inner.class
Outer.Inner.Deep.class.getNestHost() == Outer.class
Outer.Inner.class.isNestmateOf(Outer.Inner.Deep.class)
```

Cả ba đều có giá trị `true`. Ví dụ trên là **các biểu thức minh họa** (không phải một file Java độc lập có `main`).

Local class và anonymous class cũng thường được compiler gán nest host là class ngoài cùng tương ứng. Để kiểm chứng bằng chương trình độc lập, tạo **`LocalNest.java`**:

```java
public class LocalNest {
    static Class<?> localType() {
        class Local {}
        return Local.class;
    }

    static Class<?> anonymousType() {
        return new Runnable() {
            @Override
            public void run() {}
        }.getClass();
    }

    public static void main(String[] args) {
        System.out.println(localType().getNestHost() == LocalNest.class);
        System.out.println(anonymousType().getNestHost() == LocalNest.class);
    }
}
```

Chạy `javac --release 17 LocalNest.java` rồi `java LocalNest`, kết quả:

```text
true
true
```

Do đó, không nên suy luận rằng `getNestMembers()` chỉ có nested class được viết bằng cú pháp member class. Danh sách thực tế dựa trên những class file đã được sinh và được JVM xác minh.

## 8. Các tình huống đặc biệt và giới hạn

**Primitive, array, `void`:** mỗi kiểu này được coi là nest riêng; ví dụ `String[].class.getNestHost() == String[].class` là `true`, còn `String[].class.isNestmateOf(String.class)` là `false`. Đừng hiểu “array của String” đồng nghĩa là nestmate của `String`.

**Class loader:** hai kiểu nhìn như cùng package theo tên văn bản vẫn có thể khác *runtime package* nếu được định nghĩa bởi class loader khác. Quy tắc nest không vượt qua ranh giới runtime package. Với framework nạp/biến đổi bytecode, kiểm tra quan hệ nest qua API thực tế an toàn hơn suy đoán từ tên class.

**Class file không nhất quán:** nếu bytecode bị biến đổi khiến `NestHost`/`NestMembers` không phù hợp, quá trình xác định nest/truy cập `private` có thể thất bại hoặc kiểu bị xem như singleton nest tùy điều kiện xác minh. Cần kiểm tra bytecode thực tế, class loader và thông báo JVM thay vì kết luận từ tên class.

**Hidden class:** một hidden class có thể được định nghĩa với quyền nestmate theo `Lookup.defineHiddenClass` và tùy chọn `NESTMATE`, nhưng không được bảo đảm xuất hiện trong `getNestMembers()` của host. Không dùng API này làm cơ chế khám phá đầy đủ mọi class động của một framework.

**Reflection không mở khóa truy cập vô điều kiện:** `isNestmateOf` chỉ cho biết quan hệ nest; nó không tự cấp quyền cho mã ở một class khác gọi mọi method `private` bằng `Method.invoke`. Quyền truy cập phản chiếu còn phụ thuộc caller, thành viên, `AccessibleObject` và quy tắc module/encapsulation. Nếu muốn gọi method private, cần kiểm tra quyền của chính thao tác reflection đó.

## 9. Cách dùng trong thực tế

1. **Phân tích cấu trúc class:** gọi `getNestHost()` khi cần biết một member class, local class hay anonymous class thuộc host nào trong runtime.
2. **Chẩn đoán công cụ sinh/biến đổi bytecode:** kết hợp `javap -v` với `getNestMembers()` và `isNestmateOf()` để xác nhận compiler hoặc enhancer đã duy trì thông tin nest hợp lệ.
3. **Điều tra lỗi truy cập `private`:** nếu hai kiểu dự kiến là nestmate nhưng kiểm tra trả về `false`, rà soát class file, package, class loader và cách tạo kiểu động.
4. **Hiển thị metadata:** dùng `getNestMembers()` rồi sắp xếp/deduplicate theo nhu cầu hiển thị; tránh dựa vào thứ tự và đếm phần tử gốc.

Ví dụ helper kiểm tra quan hệ theo API trực tiếp:

```java
static boolean shareNest(Class<?> first, Class<?> second) {
    if (first == null || second == null) {
        return false; // chính sách của helper; API isNestmateOf(null) ném NPE
    }
    return first.isNestmateOf(second);
}
```

Helper chỉ minh họa chính sách đầu vào `null` của ứng dụng và phải đặt trong một class để biên dịch; nó không thay đổi hợp đồng của API JVM.

## 10. Lỗi hiểu sai thường gặp

- **“Hai lớp cùng package là nestmates.”** Sai: cùng package chỉ là một điều kiện liên quan; thông tin host/member còn phải khớp.
- **“Class con luôn cùng nest với class cha.”** Sai: quan hệ kế thừa và quan hệ nest độc lập.
- **“`getNestHost()` luôn trả về class bao trực tiếp.”** Sai: lớp lồng nhiều tầng thường vẫn có host là top-level class.
- **“`getNestMembers()[1]` luôn là lớp lồng đầu tiên.”** Sai: chỉ phần tử 0 được bảo đảm là host; các phần tử sau có thứ tự không xác định.
- **“`getNestMembers()` liệt kê hết mọi hidden class.”** Sai: hidden class thêm qua `defineHiddenClass` không nằm trong danh sách `NestMembers` phản ánh bởi API.
- **“Kiểm tra `isNestmateOf()` bằng `true` là có thể bypass private trên mọi đối tượng.”** Sai: quan hệ nest không vô hiệu hóa quy tắc kiểm tra truy cập hoặc cơ chế đóng gói module.
- **“Mọi nested class có host khác nhau.”** Sai: các member của cùng nest chia sẻ một host.

## 11. Tự kiểm tra kiến thức

1. Vì sao `Outer.Inner.Deep.class.getNestHost()` thường trả về `Outer.class` thay vì `Outer.Inner.class`?
2. Tại sao hai top-level class trong cùng `.java` thường không phải nestmates?
3. Khi in `getNestMembers()`, vì sao cần sắp xếp nếu muốn kết quả tái lập?
4. Khi dùng runtime code generation, vì sao không thể dùng `getNestMembers()` để liệt kê chắc chắn mọi hidden class?
5. Nestmate liên quan thế nào đến truy cập `private`, và vì sao nó không thay cho kiểm tra quyền Reflection?

**Ghi nhớ:** `getNestHost()` hỏi **host là ai**; `getNestMembers()` hỏi **những member nào được xác nhận trong nest**; `isNestmateOf(c)` hỏi **hai kiểu có chung host không**. Cả ba phản ánh quan hệ nest ở JVM (Java 11+), không thể suy ra chỉ từ package, kế thừa hoặc tên class.

## Tài liệu chuẩn

- [Java SE 17 — `Class.getNestHost`, `Class.getNestMembers`, `Class.isNestmateOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [JVMS 17 — `NestHost`/`NestMembers` và quy tắc nestmate access control](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [JVMS 17 — Class File Format, Nest Attributes](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html)
