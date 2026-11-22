# @SafeVarargs: điều kiện sử dụng và trách nhiệm với varargs trong Java

## 1. `@SafeVarargs` giải quyết vấn đề gì?

Trong Java, **varargs** cho phép phương thức nhận số lượng đối số biến đổi bằng cú pháp `T...`:

```java
static void print(String... values) {
    for (String value : values) {
        System.out.println(value);
    }
}
```

Có thể gọi `print("Java", "JVM")`; về mặt thực thi, tham số varargs được biểu diễn như **một mảng** (`String[]`). Khi phần tử của varargs là một kiểu **không reifiable** (*non-reifiable*), chẳng hạn `List<String>` hoặc tham số kiểu `T`, sự kết hợp giữa generic và mảng có thể dẫn đến **heap pollution** (ô nhiễm kiểu trên heap).

```java
static void inspect(List<String>... groups) {
    // Về cú pháp nguồn, groups có kiểu List<String>[].
}
```

Với `List<String>...`, trình biên dịch không thể đảm bảo mảng tạo ra ở mọi lời gọi bảo toàn tham số kiểu `String` tại runtime: do **type erasure**, JVM chỉ biết phần tử mảng thuộc lớp `List`, không biết `List<String>` hay `List<Integer>`. Nếu code sửa mảng qua một alias rộng hơn, dữ liệu không đúng kiểu có thể lọt vào.

`@SafeVarargs` là annotation chuẩn trong `java.lang`, dùng để **người viết phương thức hoặc constructor cam kết rằng phần thân xử lý tham số varargs một cách an toàn**. Khi được đặt hợp lệ, annotation này giúp ngăn các cảnh báo `unchecked` phát sinh vì varargs có kiểu phần tử non-reifiable, ở cả vị trí khai báo và các lời gọi liên quan.

Điều cốt lõi: **`@SafeVarargs` không khiến Java kiểm tra kiểu mạnh hơn ở runtime**. Nó là một lời bảo đảm do lập trình viên đưa ra. Nếu lời bảo đảm sai, chương trình vẫn có thể gặp `ClassCastException` hoặc hành vi lỗi khác.

## 2. Hiểu nguyên nhân: non-reifiable, mảng và heap pollution

### 2.1. Reifiable và non-reifiable

Kiểu **reifiable** là kiểu mà thông tin kiểu cần thiết vẫn xác định được ở runtime. Ví dụ điển hình: `String`, `int`, `String[]` và `List<?>` (unbounded wildcard). Kiểu **non-reifiable** không giữ đủ thông tin tham số kiểu sau erasure, chẳng hạn `List<String>`, `List<Integer>`, hoặc tham số kiểu `T`.

Với khai báo `List<String>... groups`:

1. Dạng varargs được xử lý như mảng tham số `List<String>[]` trong source code.
2. Tại runtime, mảng chứa các đối tượng `List`; không có kiểm tra phần tử bên trong danh sách có thật sự là `String` hay không.
3. Mảng Java có tính **covariant**: mảng `List[]` có thể được nhìn dưới biến kiểu `Object[]`.
4. Thao tác ghi thông qua `Object[]` có thể đưa một `List<Integer>` vào nơi mã nguồn đang tin là `List<String>`.

### 2.2. Heap pollution xảy ra như thế nào?

Đây là ví dụ **cố ý không an toàn**, minh họa cơ chế; không gắn `@SafeVarargs` lên phương thức này:

```java
import java.util.List;

class UnsafeExample {
    static void broken(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(42);
        String text = groups[0].get(0); // ClassCastException
        System.out.println(text);
    }
}
```

Trong ví dụ trên, `alias[0] = List.of(42)` vượt qua kiểm tra kiểu mảng ở runtime vì giá trị vẫn là một `List`. Sau đó, `groups[0].get(0)` được code gọi như `String`, nhưng thực chất trả về `Integer`; phép chuyển kiểu ngầm định dẫn đến `ClassCastException`.

**Không cần một phép cast tường minh sai kiểu** mới gây ra heap pollution; việc tạo alias của mảng varargs đã đủ để mở đường cho thao tác ghi không an toàn. Compiler có thể cảnh báo ở một số bước, nhưng không phải mọi đường gây lỗi đều được phát hiện.

## 3. Điều kiện được đặt `@SafeVarargs`

Java 17+ cho phép annotation này trên **constructor có varargs** và trên những **method có varargs** thuộc một trong ba nhóm `static`, `final`, hoặc `private`.

| Nơi khai báo | Hợp lệ? | Giải thích |
|---|---|---|
| `static void m(T... xs)` | Có | Method `static` không bị override |
| `final void m(T... xs)` | Có | Instance method `final` không bị override |
| `private void m(T... xs)` | Có, từ Java 9 | Instance method `private` không bị override |
| Constructor `C(T... xs)` | Có | Constructor không bị override |
| `void m(T... xs)` thông thường, có thể override | Không | Không phải `static`, `final` hay `private` |
| `void m(T[] xs)` không có `...` | Không | Đây là method thông thường, không khai báo varargs |
| Method không có tham số varargs | Không | `@SafeVarargs` chỉ dành cho khai báo có varargs |

Annotation có `@Target({ElementType.CONSTRUCTOR, ElementType.METHOD})`, vì vậy không gắn trực tiếp lên class, field hoặc parameter. Điều kiện **có varargs là bắt buộc**, và theo cú pháp Java, tham số varargs phải nằm cuối danh sách tham số. `@SafeVarargs` không thể biến một phương thức `T[]` thành phương thức varargs.

Ví dụ các khai báo hợp lệ về **vị trí đặt annotation** (mức độ an toàn còn phụ thuộc phần thân):

```java
import java.util.List;

class ValidDeclarations {
    @SafeVarargs
    static <T> void staticMethod(T... values) {}

    @SafeVarargs
    final <T> void finalMethod(List<T>... values) {}

    @SafeVarargs
    private <T> void privateMethod(List<T>... values) {}

    @SafeVarargs
    ValidDeclarations(List<String>... values) {}
}
```

Các khai báo sau **cố ý không hợp lệ** và không biên dịch được:

```java
class InvalidDeclarations {
    @SafeVarargs
    void overridable(String... values) {} // Sai: instance method có thể override

    @SafeVarargs
    static void fixedArity(String[] values) {} // Sai: không dùng ...

    @SafeVarargs
    static void noVarargs() {} // Sai: không có tham số varargs
}
```

Lưu ý: một method trong `final class` không tự thỏa điều kiện `final` của `@SafeVarargs` nếu bản thân method không được khai báo `final`, `static` hoặc `private`. Khi khai báo instance method công khai, hãy đặt `final` trực tiếp trên method nếu muốn dùng annotation này.

## 4. Trách nhiệm khi cam kết varargs là an toàn

Được phép đặt annotation theo cú pháp **chưa đủ** để khẳng định phương thức thật sự an toàn. Trước khi thêm `@SafeVarargs`, tác giả cần rà soát **toàn bộ đường đi của mảng varargs**:

1. **Không ghi phần tử sai kiểu vào mảng**: tránh cast qua `Object[]`, raw type hoặc unchecked cast rồi ghi giá trị không phù hợp với tham số kiểu dự kiến.
2. **Không làm lộ mảng varargs cho mã có thể sửa nó**: tránh trả về trực tiếp, lưu tham chiếu mảng vào trạng thái có thể truy cập hoặc đưa mảng tới API/callback không đáng tin cậy có thể giữ và thay đổi mảng.
3. **Không chuyển tiếp mảng đến một phương thức khác nếu chưa hiểu hợp đồng an toàn của phương thức đó**: một lời gọi phụ có thể làm lộ, giữ hoặc thay đổi chính mảng mà method hiện tại đang bảo đảm.
4. **Duy trì tính đúng đắn khi refactor**: nếu trước đây chỉ đọc mảng nhưng sau này thêm cast, lưu giữ hoặc chuyển tiếp, phải rà soát lại cam kết `@SafeVarargs`.
5. **Xem xét mọi đường đi**, kể cả ngoại lệ, lambda/closure giữ tham chiếu và các helper nhận `Object[]` hoặc raw `List[]`; việc các test hiện tại chạy được không chứng minh an toàn kiểu.

Một mẫu an toàn thường gặp là **chỉ đọc từng phần tử và sao chép nội dung sang cấu trúc mới**, không trả ra hay chia sẻ mảng varargs gốc:

```java
@SafeVarargs
static <T> List<T> combine(List<? extends T>... parts) {
    List<T> output = new ArrayList<>();
    for (List<? extends T> part : parts) {
        output.addAll(part);
    }
    return output;
}
```

`output` là danh sách mới, không phải mảng `parts`. Phương thức đọc các danh sách đầu vào theo hợp đồng generic và thêm phần tử vào danh sách đầu ra cùng kiểu; nó không ghi vào `parts[i]` và không phát tán alias của mảng `parts`.

**Một chú ý về trách nhiệm của caller:** `@SafeVarargs` bảo đảm cách *implementation* xử lý mảng varargs. Nó không hợp thức hóa dữ liệu sai kiểu mà caller cố ý tạo bằng raw type, unchecked cast hoặc các hành vi không an toàn khác. Đồng thời, không dùng annotation để che cảnh báo khi chưa điều tra nguồn gốc cảnh báo.

## 5. Ví dụ Java 17+ biên dịch và chạy được

Tạo tệp `Main.java` với toàn bộ nội dung sau:

```java
import java.util.ArrayList;
import java.util.List;

public class Main {
    @SafeVarargs
    static <T> List<T> combine(List<? extends T>... parts) {
        List<T> result = new ArrayList<>();
        for (List<? extends T> part : parts) {
            result.addAll(part);
        }
        return result;
    }

    static class Bundle {
        private final List<String> entries;

        @SafeVarargs
        Bundle(List<String>... parts) {
            List<String> copy = new ArrayList<>();
            for (List<String> part : parts) {
                copy.addAll(part);
            }
            entries = List.copyOf(copy);
        }

        List<String> entries() {
            return entries;
        }

        @SafeVarargs
        private void consume(List<String>... parts) {
            for (List<String> part : parts) {
                System.out.println(part);
            }
        }
    }

    public static void main(String[] args) {
        List<String> merged = combine(
                List.of("Java", "Spring"),
                List.of("JVM"));
        System.out.println("Merged: " + merged);

        Bundle bundle = new Bundle(List.of("A"), List.of("B"));
        System.out.println("Bundle: " + bundle.entries());
    }
}
```

Từ thư mục chứa `Main.java`, thực hiện:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Đầu ra:

```text
Merged: [Java, Spring, JVM]
Bundle: [A, B]
```

Trong ví dụ này:

- `combine()` là generic static varargs method và không sửa hoặc làm lộ mảng `parts`.
- Constructor `Bundle(List<String>... parts)` được phép đặt `@SafeVarargs`; nó sao chép dữ liệu vào danh sách mới, sau đó dùng `List.copyOf` tạo danh sách bất biến.
- `consume()` minh họa `@SafeVarargs` trên private instance method (hợp lệ từ Java 9); đoạn code biên dịch nhưng method này không được gọi trong `main`, vì vậy không tạo thêm stdout.

Điểm cần hiểu: mảng `parts` có thể dùng trong phương thức mà không gây heap pollution; sự nguy hiểm xuất hiện khi thao tác mảng hoặc bí mật truyền alias của nó làm đổ vỡ kỳ vọng về kiểu dữ liệu.

## 6. Ví dụ phản chứng: đặt annotation hợp lệ nhưng cam kết sai

Đoạn sau **biên dịch theo cú pháp `@SafeVarargs`**, nhưng **không bao giờ nên dùng annotation như vậy trong ứng dụng thực**:

```java
import java.util.List;

class FalsePromise {
    @SafeVarargs // CAM KẾT SAI: phần thân cố tình gây heap pollution
    static void corrupt(List<String>... values) {
        Object[] alias = values;
        alias[0] = List.of(123);
        String text = values[0].get(0); // ClassCastException
        System.out.println(text);
    }
}
```

`corrupt()` là `static` và có `...`, nên vị trí đặt annotation hợp lệ. Nhưng `alias[0] = List.of(123)` vi phạm cam kết type safety. **Trình biên dịch không chứng minh toàn bộ phần thân an toàn chỉ vì thấy `@SafeVarargs`**. Tùy mức cảnh báo, compiler còn có thể cảnh báo về thao tác đáng ngờ trong phần thân; vì thế `@SafeVarargs` cũng không có nghĩa là dập mọi warning.

Ví dụ này cho thấy lý do annotation có phạm vi áp dụng hẹp: với method bị override, một subclass có thể thay implementation bằng code không an toàn trong khi người gọi vẫn nhận một lời bảo đảm từ khai báo ban đầu. Các quy tắc `static`, `final` và `private` loại bỏ khả năng override theo cách đó.

## 7. Warning nào được xử lý? Phân biệt `@SafeVarargs` và `@SuppressWarnings`

Khi method khai báo một varargs có kiểu phần tử non-reifiable, Java có thể cảnh báo ở:

- **Nơi khai báo:** `Possible heap pollution from parameterized vararg type ...` (câu chữ phụ thuộc compiler).
- **Nơi gọi:** `Unchecked generic array creation for varargs parameter ...` (compiler cần tạo mảng tương ứng với lời gọi có kiểu generic).

Nếu method thật sự an toàn, `@SafeVarargs` loại bỏ các cảnh báo `unchecked` liên quan đến **khai báo** và **những lời gọi** đó; tác động tới call site là khác biệt quan trọng.

Trong khi đó, `@SuppressWarnings("unchecked")` chỉ triệt tiêu loại warning tương ứng tại **phạm vi được đặt annotation**. Đặt annotation này trong phương thức không phải một cam kết varargs có hiệu lực loại warning tại tất cả call site như `@SafeVarargs`.

| Tiêu chí | `@SafeVarargs` | `@SuppressWarnings("unchecked")` |
|---|---|---|
| Mục đích | Cam kết varargs non-reifiable được xử lý an toàn | Tắt cảnh báo unchecked trong phạm vi được đánh dấu |
| Ảnh hưởng tới các call site | Có, đối với cảnh báo unchecked do tạo mảng varargs | Không tự động áp dụng đến các call site khác |
| Giới hạn vị trí | Chỉ constructor/method varargs đủ điều kiện | Nhiều loại declaration, không giới hạn riêng cho varargs |
| Kiểm tra an toàn tại runtime | Không | Không |

Đừng mặc định `@SafeVarargs` bảo đảm compiler không bao giờ cảnh báo nữa. Các cảnh báo khác như `rawtypes`, `cast` hoặc `varargs` trong thân phương thức có thể vẫn xuất hiện khi bật `javac -Xlint`; cần đọc chúng để tìm code rủi ro thay vì tắt thêm một cách mù quáng.

Một ví dụ đối chứng **dùng để minh họa warning**, không phải chương trình `Main.java` độc lập:

```java
static void withoutPromise(List<String>... lists) {
    // Giả sử implementation được review là an toàn.
    for (List<String> list : lists) {
        System.out.println(list);
    }
}

@SafeVarargs
static void withPromise(List<String>... lists) {
    for (List<String> list : lists) {
        System.out.println(list);
    }
}
```

Khai báo đầu có thể tạo cảnh báo về non-reifiable varargs, cả ở declaration và call site. Khai báo sau thể hiện cam kết đã review để compiler tránh các warning unchecked của trường hợp đó. Không thêm annotation chỉ vì mục tiêu báo cáo số warning bằng 0.

## 8. Những hiểu nhầm và lỗi thường gặp

### 8.1. Dùng `@SafeVarargs` cho mọi varargs

Với `String... values`, `int... numbers`, kiểu phần tử vốn reifiable. Không có lý do thông thường để dùng `@SafeVarargs`; compiler có thể cảnh báo annotation là dư thừa. Hãy sử dụng khi phần tử varargs có thể gây unchecked warning liên quan đến non-reifiable type.

### 8.2. Tưởng `final` trên biến mảng là đủ

```java
static void demo(final List<String>... lists) {
    Object[] alias = lists;
    alias[0] = List.of(42);
}
```

`final` ở tham số chỉ ngăn **gán lại biến tham chiếu** `lists`, không ngăn sửa phần tử bên trong mảng. Nó cũng không thay điều kiện: annotation đòi **method `final`** (hoặc `static`, `private`, constructor), không phải tham số `final`.

### 8.3. Trả lại trực tiếp mảng varargs hoặc cất mảng vào field

```java
@SafeVarargs
static <T> T[] leak(T... values) {
    return values; // Làm lộ đúng mảng mà caller/method đang dựa vào.
}
```

Dù đoạn khai báo có thể được biên dịch, việc trả mảng generic gốc làm mất quyền kiểm soát alias; người nhận có thể sửa nó theo đường không an toàn. Theo nguyên tắc review chặt chẽ, đây **không phải mẫu nên tự tin gắn `@SafeVarargs`**. Nếu cần kết quả, nên xác định một API trả danh sách hoặc cấu trúc đã sao chép thích hợp, phù hợp yêu cầu về biến đổi và null.

### 8.4. Nhầm "không phát sinh warning" với "đã type-safe"

Một method được annotate sai vẫn có thể ném `ClassCastException` tại runtime. Warning là công cụ phát hiện nguy cơ của compiler; việc suppress warning không xóa nguy cơ hoặc thay đổi phép kiểm tra mảng ở runtime.

### 8.5. Quên tính hợp lệ khi đổi access modifier

Đổi một method từ `private` thành package-private/public, hoặc bỏ `final`, có thể làm mất điều kiện hợp lệ để đặt `@SafeVarargs`. Sau refactor phải xem lại cả khả năng override và hợp đồng an toàn của body.

## 9. Checklist trước khi gắn annotation

- Phương thức/constructor **thật sự có `...`** hay mới chỉ nhận mảng `[]`?
- Nếu là method, nó được khai báo **`static`, `final` hoặc `private`** (trên Java 9+) hay chưa?
- Kiểu phần tử varargs **non-reifiable** và cảnh báo cần xử lý có thực sự xuất phát từ varargs generic hay không?
- Trong mọi đường thực thi, code có **chỉ đọc** hoặc sử dụng các phần tử theo đúng hợp đồng generic, tránh ghi vào mảng qua alias không an toàn?
- Có đường nào **return, store, publish, capture** hoặc truyền mảng varargs tới helper làm lộ khả năng sửa mảng không?
- Các thay đổi sau này có thể phá hợp đồng mà annotation đã cam kết với **mọi caller** không?

Nếu không thể tự tin trả lời, hãy sửa thiết kế trước: ví dụ nhận `List<T>` thay vì generic varargs, hoặc bảo đảm sao chép dữ liệu và không làm lộ mảng. Không gắn `@SafeVarargs` như một thao tác dọn cảnh báo máy móc.

## 10. Tài liệu chuẩn để đối chiếu

- [Java SE 17 API — `java.lang.SafeVarargs`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html): định nghĩa, compiler restrictions, ý nghĩa cảnh báo và ví dụ heap pollution.
- [Java Language Specification — §9.6.4.7 `@SafeVarargs`](https://docs.oracle.com/javase/specs/jls/se16/html/jls-9.html#jls-9.6.4.7): cam kết của người viết phương thức và tác động tới cảnh báo ở call site.
- [Oracle Java Tutorials — Non-Reifiable Types](https://docs.oracle.com/javase/tutorial/java/generics/nonReifiableVarargsType.html): cơ chế erasure, heap pollution và generic varargs.

**Ghi nhớ:** `@SafeVarargs` là **lời cam kết về implementation** của method/constructor varargs, được Java cho phép tại các declaration không thể override. Lập trình viên phải chứng minh code không làm hỏng tính đúng đắn của các phần tử qua mảng generic; annotation chỉ triệt tiêu một nhóm warning tương ứng và không cung cấp lá chắn runtime.