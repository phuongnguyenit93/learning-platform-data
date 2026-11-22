# Kiểm thử annotation lặp, kiểu chứa và thứ tự kết quả trong Java

Trong Java, một **repeatable annotation** là loại annotation có thể xuất hiện nhiều lần ở cùng một vị trí, ví dụ:

```java
@Tag("first")
@Tag("second")
class Pair {}
```

Cú pháp này hoạt động khi `Tag` được đánh dấu `@Repeatable(Tags.class)` và có **containing annotation type** `Tags` với phần tử bắt buộc `Tag[] value()`. Khi biên dịch, hai lần xuất hiện `@Tag` được biểu diễn **qua một container `@Tags`**. Vì vậy, các API Reflection thông thường và các API chuyên hỗ trợ repeatable annotation có thể trả **những kết quả khác nhau dù cùng hỏi về một lớp**.

Bài học này tập trung vào **kiểm thử và phát hiện lỗi**, không chỉ khai báo cú pháp. Ta sẽ kiểm tra chính xác:

- Một annotation đơn có được đọc trực tiếp không.
- Hai annotation lặp có được chứa trong `Tags` và trả ra đúng **thứ tự** không.
- Container viết tường minh và container rỗng cho kết quả nào.
- Sự khác biệt giữa `getAnnotation`, `getDeclaredAnnotation`, `getDeclaredAnnotations`, `getAnnotationsByType` và `getDeclaredAnnotationsByType`.
- `@Inherited` ảnh hưởng kết quả trên class con ra sao, và đâu là giới hạn khi kiểm tra method/parameter.
- Những lỗi định nghĩa container hoặc retention nào phải bị compiler từ chối hoặc khiến test đọc được mảng rỗng.
- Cách kết hợp **test chạy thực tế, phép kiểm tra có thông báo lỗi rõ ràng và `javap -v`** để xác minh dấu vết bytecode.

Ví dụ đầy đủ chạy bằng **JDK 17+**, chỉ cần JDK, không cần thư viện kiểm thử bên ngoài. Các phép kiểm tra chủ động ném `AssertionError` nếu điều kiện sai, nên không phụ thuộc việc JVM có bật `-ea` hay không.

## 1. Các khái niệm cần phân biệt khi viết test

### Annotation được lặp và annotation chứa

Ví dụ định nghĩa đúng:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}
```

- `Tag` là **repeated annotation type**. `Tag.value()` trả một `String`.
- `Tags` là **container annotation type**. `Tags.value()` trả **`Tag[]`**, không phải `String[]`.
- `@Repeatable(Tags.class)` trên `Tag` cho compiler biết nên dùng `Tags` khi có nhiều `@Tag` cùng vị trí.
- `@Retention(RUNTIME)` được đặt trên **cả hai loại** để chương trình có thể đọc metadata bằng Java Reflection chuẩn.
- `@Target(TYPE)` giới hạn các vị trí dùng cho ví dụ trên class. Nếu muốn thử method và parameter, phải mở rộng target phù hợp.

**Một lần `@Tag` không đồng nghĩa luôn có `@Tags`.** Khi chỉ một `@Tag` xuất hiện tại một vị trí, nó có thể được biểu diễn trực tiếp, không cần compiler tạo lần sử dụng container.

### Bốn trạng thái test cơ bản

| Tình huống | Cách viết | Điều cần kiểm thử |
| --- | --- | --- |
| Một annotation | `@Tag("solo")` | Nhìn thấy `Tag` trực tiếp; không tự suy ra container |
| Nhiều annotation lặp | `@Tag("first") @Tag("second")` | Container biểu diễn `Tag[2]`; API by-type trả đúng thứ tự |
| Container tường minh | `@Tags({@Tag("a"), @Tag("b")})` | API by-type mở container như trường hợp lặp |
| Container rỗng | `@Tags({})` | Container tồn tại nhưng tập `Tag` có độ dài 0 |

Mỗi trạng thái kiểm tra một hợp đồng khác nhau. **Chỉ test trường hợp nhiều annotation rồi bỏ qua single/empty là chưa đủ** cho code đọc metadata tổng quát.

## 2. Chọn đúng API Reflection để kiểm thử

Các phương thức sau thuộc nhóm `AnnotatedElement` và có các quy tắc riêng:

| API | Câu hỏi kiểm thử | Lưu ý khi có `@Tag` lặp |
| --- | --- | --- |
| `getDeclaredAnnotation(Tag.class)` | Có một `Tag` được khai báo trực tiếp ở phần tử này không? | **Không tự mở container** |
| `getAnnotation(Tag.class)` | Có một `Tag` "present" theo quy tắc API không? | Không phải thao tác lấy `Tag` đầu tiên của một danh sách lặp |
| `getDeclaredAnnotation(Tags.class)` | Container `Tags` có khai báo trực tiếp không? | Đọc `Tags.value()` để xem mảng con |
| `getDeclaredAnnotations()` | Những annotation runtime-visible nào được coi là khai báo trực tiếp? | Hai `@Tag` có thể hiện như một `Tags` |
| `getDeclaredAnnotationsByType(Tag.class)` | Những `Tag` **directly/indirectly present** tại chính phần tử này là gì? | **Mở container**, giữ thứ tự các `Tag` |
| `getAnnotationsByType(Tag.class)` | Những `Tag` **associated** với phần tử này là gì? | Mở container; với class có `@Inherited` có thể tìm superclass |

Ví dụ nếu một class có hai `@Tag` được compile thành `Tags`, việc gọi:

```java
Pair.class.getDeclaredAnnotation(Tag.class)
```

trả `null` trong ví dụ chuẩn, nhưng:

```java
Pair.class.getDeclaredAnnotationsByType(Tag.class)
```

trả mảng hai `Tag`. Hai kết quả này **không mâu thuẫn**: một API tìm một annotation trực tiếp, còn API kia tìm theo loại và **mở container**.

**Quy tắc chọn API:** nếu mục tiêu là lấy toàn bộ annotation cùng loại, kể cả trường hợp chỉ một, lặp nhiều hoặc container tường minh, ưu tiên `getDeclaredAnnotationsByType(T.class)` (không kế thừa) hoặc `getAnnotationsByType(T.class)` (có xét quy tắc associated và thừa kế phù hợp).

Không viết test giả định `getAnnotation(Tag.class)` tương đương với `getAnnotationsByType(Tag.class)[0]`. Hai phép gọi có hợp đồng khác nhau và truy vấn đầu có thể trả `null`.

## 3. Thứ tự được bảo đảm ở đâu?

Với hai annotation cùng loại được viết:

```java
@Tag("first")
@Tag("second")
class Pair {}
```

compiler biểu diễn chúng bằng một `Tags` có mảng `Tag[]` theo **thứ tự xuất hiện của các annotation lặp**. Theo đó, `getDeclaredAnnotationsByType(Tag.class)` trả các phần tử `Tag` theo thứ tự **`first` trước `second`** trong ví dụ.

Bạn có thể kiểm tra bằng giá trị cụ thể:

```java
Tag[] values = Pair.class.getDeclaredAnnotationsByType(Tag.class);
String[] names = {
    values[0].value(),
    values[1].value()
};
```

Đoạn này là snippet trong một phương thức; trước khi index phải bảo đảm mảng có độ dài 2. Trong bài test đầy đủ, ta so **cả mảng** thay vì chỉ nhìn giá trị đầu.

### Giới hạn của bảo đảm thứ tự

Cần phân biệt hai loại thứ tự:

1. **Thứ tự các annotation lặp của cùng một loại** như `@Tag("first") @Tag("second")`, được biểu diễn thành mảng bên trong container và được API by-type trả theo thứ tự.
2. **Thứ tự giữa các annotation thuộc những loại khác nhau** khi duyệt kết quả của `getDeclaredAnnotations()` hoặc một tập `Map` metadata. Không thiết kế test phụ thuộc vào thứ tự tùy ý giữa các loại annotation không liên quan, trừ khi API cụ thể cam kết điều đó.

Ví dụ:

```java
@Tag("first")
@Tag("second")
@OtherAnnotation
class Pair {}
```

Nếu có `OtherAnnotation` được khai báo hợp lệ, việc lấy toàn bộ declaration annotations rồi so rằng `Tags` nhất thiết đứng ở index 0 trong mọi tình huống là một test dễ giòn. Hãy **lọc theo loại** hoặc dùng API by-type, rồi chỉ kiểm tra thứ tự **bên trong danh sách `Tag`**.

Cũng không coi thứ tự trong mảng là một hệ thống ưu tiên nghiệp vụ mặc định. Nếu annotation thể hiện các quy tắc có thể xung đột, hãy định nghĩa rõ rule đầu ưu tiên hay cuối ưu tiên và kiểm tra chính sách đó riêng.

## 4. Bộ kiểm thử Java 17+ hoàn chỉnh, không cần JUnit

Tạo một file **`RepeatableAnnotationTests.java`** với nội dung:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.Arrays;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD, ElementType.PARAMETER})
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD, ElementType.PARAMETER})
@interface Tags {
    Tag[] value();
}

@Tag("first")
@Tag("second")
class Pair {
}

@Tag("single")
class Single {
}

@Tags({@Tag("manual-1"), @Tag("manual-2")})
class Explicit {
}

@Tags({})
class Empty {
}

class Child extends Pair {
}

@Tag("child")
class ChildOverride extends Pair {
}

class Handler {
    @Tag("check")
    @Tag("audit")
    public void run(
            @Tag("required") @Tag("logged") String value) {
    }
}

public class RepeatableAnnotationTests {
    static int passed = 0;

    static void eq(String label, Object expected, Object actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
        passed++;
    }

    static String values(Tag[] annotations) {
        return Arrays.toString(
                Arrays.stream(annotations)
                        .map(Tag::value)
                        .toArray(String[]::new));
    }

    static String nullToText(Object object) {
        return object == null ? "null" : object.toString();
    }

    public static void main(String[] args) throws Exception {
        eq("pair by type", "[first, second]",
                values(Pair.class.getDeclaredAnnotationsByType(Tag.class)));

        eq("pair declared container", Tags.class,
                Pair.class.getDeclaredAnnotations()[0].annotationType());

        eq("pair container order", "[first, second]",
                values(Pair.class.getDeclaredAnnotation(Tags.class).value()));

        eq("pair direct Tag absent", "null",
                nullToText(Pair.class.getDeclaredAnnotation(Tag.class)));

        eq("single Tag", "[single]",
                values(Single.class.getDeclaredAnnotationsByType(Tag.class)));

        eq("single direct type", Tag.class,
                Single.class.getDeclaredAnnotations()[0].annotationType());

        eq("single container absent", "null",
                nullToText(Single.class.getDeclaredAnnotation(Tags.class)));

        eq("explicit container", "[manual-1, manual-2]",
                values(Explicit.class.getDeclaredAnnotationsByType(Tag.class)));

        eq("empty container", "[]",
                values(Empty.class.getDeclaredAnnotationsByType(Tag.class)));

        eq("empty direct container", 0,
                Empty.class.getDeclaredAnnotation(Tags.class).value().length);

        eq("child declared no tags", 0,
                Child.class.getDeclaredAnnotationsByType(Tag.class).length);

        eq("child inherited order", "[first, second]",
                values(Child.class.getAnnotationsByType(Tag.class)));

        eq("child local overrides", "[child]",
                values(ChildOverride.class.getAnnotationsByType(Tag.class)));

        Method run = Handler.class.getDeclaredMethod("run", String.class);

        eq("method pair", "[check, audit]",
                values(run.getDeclaredAnnotationsByType(Tag.class)));

        Parameter param = run.getParameters()[0];

        eq("parameter pair", "[required, logged]",
                values(param.getAnnotationsByType(Tag.class)));

        eq("parameter container", 2,
                param.getAnnotation(Tags.class).value().length);

        System.out.println("PASS " + passed + " checks");
        System.out.println("Pair: "
                + values(Pair.class.getDeclaredAnnotationsByType(Tag.class)));
        System.out.println("Single: "
                + values(Single.class.getDeclaredAnnotationsByType(Tag.class)));
        System.out.println("Explicit: "
                + values(Explicit.class.getDeclaredAnnotationsByType(Tag.class)));
        System.out.println("Child: "
                + values(Child.class.getAnnotationsByType(Tag.class)));
        System.out.println("Override: "
                + values(ChildOverride.class.getAnnotationsByType(Tag.class)));
        System.out.println("Method: "
                + values(run.getDeclaredAnnotationsByType(Tag.class)));
        System.out.println("Parameter: "
                + values(param.getAnnotationsByType(Tag.class)));
    }
}
```

**Ghi chú về `@Inherited`:** ví dụ dùng `@Inherited` trên cả `Tag` và `Tags` để có thể kiểm tra `Child` kế thừa các `Tag` của `Pair` theo quy tắc truy vấn trên **class**. Meta-annotation này **không** làm annotation trên method hoặc parameter tự động được kế thừa. `@Target` bao gồm `TYPE`, `METHOD`, `PARAMETER` để kiểm tra cả ba vị trí trong cùng một ví dụ.

Các loại `Tag`, `Tags`, `Pair`, `Single`… ở package mặc định và chỉ có một `public class` để file chạy độc lập. Trong ứng dụng thực tế hãy đặt chúng trong package rõ ràng; các nguyên tắc kiểm thử không thay đổi.

### 4.1. Chạy test

Trong thư mục có file:

```bash
javac --release 17 RepeatableAnnotationTests.java
java RepeatableAnnotationTests
```

Stdout chính xác:

```text
PASS 16 checks
Pair: [first, second]
Single: [single]
Explicit: [manual-1, manual-2]
Child: [first, second]
Override: [child]
Method: [check, audit]
Parameter: [required, logged]
```

**Đã kiểm chứng:** file Java được biên dịch thành công với `javac --release 17` và chạy trên JDK; 16 phép kiểm tra đều pass và stdout đúng như trên.

### 4.2. Vì sao dùng hàm eq() tự ném AssertionError?

Hàm `eq(label, expected, actual)` kiểm tra kết quả **đúng bằng dữ liệu mong đợi**. Khi có khác biệt, test dừng bằng:

```text
java.lang.AssertionError: <label>: expected=<...>, actual=<...>
```

Đây là **mẫu định dạng thông báo lỗi**, không phải một lỗi xảy ra trong lần chạy thành công. Thông báo thực tế sẽ có label và giá trị cụ thể.

Java có cú pháp `assert`, nhưng nếu viết test dựa vào `assert` thì phải chạy với `java -ea` để bật assertion. Bộ test ở đây gọi `throw new AssertionError(...)` trực tiếp nên không phụ thuộc vào flag `-ea`. Điều đó làm câu lệnh `java RepeatableAnnotationTests` đủ để xác minh.

Hàm `values(...)` chuyển mảng annotation thành chuỗi theo **đúng thứ tự** mà Reflection trả về. Nếu đảo `first` và `second` thì phép kiểm tra so với `[first, second]` sẽ thất bại thay vì chỉ thấy số lượng 2 và tưởng rằng test đã đủ.

## 5. Giải thích 16 phép kiểm tra

### 5.1. Pair — compiler dùng một container cho hai Tag

```java
@Tag("first")
@Tag("second")
class Pair {}
```

Các phép kiểm tra:

- `getDeclaredAnnotationsByType(Tag.class)` phải trả thứ tự `[first, second]`.
- `Pair.class.getDeclaredAnnotations()[0].annotationType()` là `Tags.class` **trong ví dụ Pair chỉ khai báo một loại annotation container ở class**, nên index 0 hợp lệ. Không suy rộng index này sang class có nhiều loại annotation khác.
- `getDeclaredAnnotation(Tags.class).value()` có mảng hai `Tag` cùng thứ tự.
- `getDeclaredAnnotation(Tag.class)` trả `null` do `Tag` lặp được biểu diễn gián tiếp trong container.

Ba API cho ba góc nhìn khác nhau: **dạng khai báo trực tiếp**, **container vật lý**, và **danh sách Tag theo loại**. Test tốt nên kiểm tra nhiều hơn chỉ độ dài mảng.

### 5.2. Single — chỉ một Tag, không bắt buộc có Tags

```java
@Tag("single")
class Single {}
```

Trong ví dụ:

- `getDeclaredAnnotationsByType(Tag.class)` trả `[single]`.
- `getDeclaredAnnotations()[0].annotationType()` là `Tag.class`.
- `getDeclaredAnnotation(Tags.class)` trả `null`.

Nếu code production chỉ đi tìm container mà không xử lý `Tag` đơn, nó sẽ **bỏ sót trường hợp hợp lệ**.

### 5.3. Explicit — container viết tường minh

```java
@Tags({@Tag("manual-1"), @Tag("manual-2")})
class Explicit {}
```

`getDeclaredAnnotationsByType(Tag.class)` trả `[manual-1, manual-2]`. Tức người dùng có thể viết container trực tiếp trong source mà kết quả API by-type vẫn giải mã đúng hai `Tag`.

Về mặt dữ liệu, container tường minh và compiler container cho nhiều annotation lặp có thể mang cùng cấu trúc metadata; **không nhất thiết khôi phục được chính xác cú pháp source từ class file**.

### 5.4. Empty — container có mảng rỗng

```java
@Tags({})
class Empty {}
```

Có `Tags` trực tiếp, nhưng `getDeclaredAnnotationsByType(Tag.class)` trả `[]` và `getDeclaredAnnotation(Tags.class).value().length` bằng 0. Đây là lý do test cần kiểm tra **nội dung và số phần tử**, không chỉ xem `Tags` có mặt hay không.

### 5.5. Child — kế thừa từ class cha

```java
class Child extends Pair {}
```

`Child` không khai báo `Tag` tại lớp hiện tại. Vì `Tag` và `Tags` có `@Inherited`, `Child.class.getAnnotationsByType(Tag.class)` nhận `[first, second]` từ superclass, nhưng `Child.class.getDeclaredAnnotationsByType(Tag.class)` trả mảng rỗng.

Kiểm tra cả hai API giúp không nhầm giữa **được associated qua kế thừa** và **được khai báo tại lớp con**.

### 5.6. ChildOverride — Tag tại con thay thế, không nối thêm

```java
@Tag("child")
class ChildOverride extends Pair {}
```

`getAnnotationsByType(Tag.class)` trả **`[child]`**, không phải `[first, second, child]`.

Hệ thống muốn gộp annotation của nhiều tầng class cần **viết chính sách merge riêng**, chẳng hạn tự duyệt `getSuperclass()` rồi lấy `getDeclaredAnnotationsByType` ở từng tầng. `@Inherited` không tự cộng dồn danh sách của cha và con khi con đã có annotation cùng loại.

### 5.7. Method và parameter — thứ tự ở đúng vị trí khai báo

```java
class Handler {
    @Tag("check") @Tag("audit")
    public void run(@Tag("required") @Tag("logged") String value) {}
}
```

Test lấy đúng method theo tên và danh sách kiểu tham số:

```java
Method run = Handler.class.getDeclaredMethod("run", String.class);
```

Sau đó:

- `run.getDeclaredAnnotationsByType(Tag.class)` trả `[check, audit]`.
- `run.getParameters()[0].getAnnotationsByType(Tag.class)` trả `[required, logged]`.
- `parameter.getAnnotation(Tags.class).value().length` bằng 2.

Annotation trên **method declaration** và annotation trên **parameter declaration** là hai vị trí khác nhau. Một test đọc nhầm method thay cho parameter có thể nhận đúng loại `Tag` nhưng sai giá trị.

`@Inherited` không khiến các annotation này truyền từ một method cha sang method override. Test class inheritance và test method declaration là hai trường hợp độc lập.

## 6. Kiểm chứng bằng bytecode với javap -v

Test Reflection mới trả lời “API runtime nhìn thấy gì”. Để kiểm tra **compiler đã mã hóa annotation lặp như thế nào**, dùng công cụ JDK `javap`:

```bash
javap -v -p Pair
javap -v -p Single
javap -v -p Explicit
javap -v -p Empty
```

Nếu đã compile vào một thư mục khác bằng `javac -d out`, bổ sung `-classpath out`:

```bash
javap -v -p -classpath out Pair
```

Tại phần metadata của **Pair.class**, tìm thuộc tính:

```text
RuntimeVisibleAnnotations:
    ... Tags(
        value = [ ... Tag(value="first"), ... Tag(value="second") ]
    )
```

Đây là **sơ đồ nội dung rút gọn**, không phải copy verbatim từ `javap`. Các chỉ số constant-pool và cách in descriptor khác theo JDK. Ba điều cần xác minh:

1. `Pair.class` có metadata declaration trong `RuntimeVisibleAnnotations` vì retention là `RUNTIME`.
2. Annotation ở cấp trực tiếp là **`Tags`**, tức **container**.
3. Phần tử `value` bên trong container chứa **hai annotation `Tag` theo thứ tự first, second**.

Với `Single.class`, metadata ở lớp là `Tag` trực tiếp, **không tự sinh container chỉ vì Tag có thể lặp**. Với `Explicit.class` và `Empty.class`, thấy container `Tags` tường minh; mảng lần lượt có hai và không có phần tử.

**Đã kiểm chứng bằng công cụ JDK:** lệnh `javap -v` trên `Pair.class` đã xác nhận sự hiện diện của container `Tags` trong `RuntimeVisibleAnnotations`. Không cần phụ thuộc vào thư viện đọc bytecode ngoài JDK để xác minh bước này.

### Retention CLASS sẽ khác gì?

Nếu cặp annotation có `@Retention(CLASS)`, compiler vẫn giữ metadata trong `.class` theo thuộc tính kiểu `RuntimeInvisibleAnnotations`, nhưng Java Reflection chuẩn **không trả** các annotation đó. Vì vậy:

```java
type.getDeclaredAnnotationsByType(Tag.class)
```

có thể trả mảng rỗng dù bytecode chứa annotation nếu `Tag` không có retention `RUNTIME`. Khi đó đừng kết luận compiler làm mất dữ liệu; dùng `javap -v` để kiểm tra class file, hoặc đổi retention thành `RUNTIME` nếu mục tiêu thật sự là đọc bằng Reflection.

**Không trộn test bytecode với test Reflection:** `javap` đọc file `.class`, còn `getDeclaredAnnotationsByType` đọc metadata theo API runtime. Hai đường truy cập có mục đích riêng.

## 7. Kiểm thử thứ tự: cần kiểm tra cả kích thước, nội dung và vị trí

Bài kiểm thử tốt có ba lớp kiểm tra:

**Lớp 1 — kích thước:**

```java
Tag[] tags = Pair.class.getDeclaredAnnotationsByType(Tag.class);
if (tags.length != 2) {
    throw new AssertionError("Expected two tags");
}
```

**Lớp 2 — nội dung:**

```java
if (!"first".equals(tags[0].value())) {
    throw new AssertionError("Wrong first tag");
}
```

**Lớp 3 — thứ tự toàn dãy:**

```java
String actual = values(tags);
eq("pair ordered values", "[first, second]", actual);
```

Các đoạn trên là snippet đặt bên trong lớp `RepeatableAnnotationTests` sau khi có các helper `values` và `eq`, không phải file riêng để compile.

Chỉ kiểm tra `tags.length == 2` có thể bỏ sót trường hợp `[second, first]`. Kiểm tra một giá trị đầu tiên cũng bỏ sót sai lệch ở phần tử thứ hai. Đối với metadata có thứ tự, hãy so **toàn bộ dãy đã đọc** với chuỗi/array mong đợi.

Trong test production, có thể dùng `List<String>` hoặc `String[]` cùng `Arrays.equals(...)` để so sánh rõ ràng thay vì chuỗi tạo bởi `Arrays.toString(...)`. Ví dụ bài này dùng chuỗi vì dễ hiển thị và đối chiếu stdout.

## 8. Những trường hợp cần kiểm thử để tránh bỏ sót

| Trường hợp | Test cần có | Vì sao |
| --- | --- | --- |
| Không gắn annotation | By-type trả mảng rỗng | Consumer phải xử lý tình huống không có metadata |
| Gắn một lần | By-type trả một phần tử; container có thể không có | Không được chỉ xử lý container |
| Gắn hai lần | By-type trả hai, đúng thứ tự | Kiểm tra compiler/Reflection phối hợp |
| Gắn nhiều hơn hai lần | By-type trả đủ và đúng thứ tự | Không hardcode giới hạn 2 |
| Container tường minh | Trả phần tử từ `value()` | Source có thể viết container |
| Container rỗng | Container có nhưng by-type rỗng | Không nhầm tồn tại container với tồn tại Tag |
| Annotation trên method/parameter | Đúng element/parameter được hỏi | Phạm vi metadata khác class |
| Không có retention RUNTIME | Reflection không đọc được | Phân biệt lỗi retention với lỗi repeatable |
| Lớp con không khai báo Tag | Associated API có thể tìm superclass | Kiểm tra `@Inherited` |
| Lớp con có Tag riêng | Danh sách con không tự cộng với danh sách cha | Tránh hiểu sai merge |

Cần cẩn trọng với thứ tự khi annotation trải qua **các class trong chuỗi kế thừa**. `getAnnotationsByType` không phải API nối tất cả annotation của mọi superclass thành một chuỗi duy nhất; nó tuân theo quy tắc associated annotations. Thứ tự của những phần tử được trả trong một bộ `Tag` từ một nơi khai báo/container vẫn được bảo toàn.

### Kiểm thử nhiều phần tử hơn hai

Bạn có thể thêm class:

```java
@Tag("first")
@Tag("middle")
@Tag("last")
class Triple {
}
```

Rồi kiểm tra:

```java
eq("triple order", "[first, middle, last]",
        values(Triple.class.getDeclaredAnnotationsByType(Tag.class)));
```

Đây là phần mở rộng **minh họa** của file chính; cần thêm `Triple` vào cùng file trước khi chạy. Nó xác minh logic không mặc định số phần tử là 2.

## 9. Lỗi biên dịch khi khai báo repeatable/container sai

Các ví dụ dưới đây **cố ý sai**, không ghép chúng với chương trình chạy ở mục 4.

### 9.1. Lặp một loại không có @Repeatable

```java
@interface Flag {
    String value();
}

@Flag("one")
@Flag("two")
class Wrong {
}
```

Compiler từ chối vì `Flag` không phải loại annotation repeatable. Chỉ đặt hai dòng cùng loại ở source **không làm nó tự lặp được**.

**Sửa:** định nghĩa container hợp lệ:

```java
@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@interface Flags {
    Flag[] value();
}
```

Đoạn sửa cần import `java.lang.annotation.Repeatable`. Nếu định đọc bằng Reflection, còn phải thêm retention phù hợp trên cả hai.

### 9.2. Container trả sai kiểu

```java
@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@interface Flags {
    String[] value(); // Sai: phải trả Flag[].
}
```

Chữ ký container luôn yêu cầu `Flag[] value()`, không phải mảng của dữ liệu bên trong `Flag.value()`. `String[]` không thể thay thế cho mảng annotation `Flag[]`.

### 9.3. Container thiếu phần tử tên value

```java
@Repeatable(Flags.class)
@interface Flag {}

@interface Flags {
    Flag[] items(); // Sai tên element.
}
```

Compiler cần **`Flag[] value()`**, không phải `items()`, `getItems()` hay `annotations()`.

### 9.4. Container có phần tử bổ sung không có default

```java
@Repeatable(Flags.class)
@interface Flag {}

@interface Flags {
    Flag[] value();
    String owner(); // Không có default.
}
```

Khi compiler đóng gói nhiều `@Flag` vào container, nó không có giá trị cho `owner`. Nếu cần phần tử phụ, khai báo một `default` thích hợp:

```java
String owner() default "system";
```

Dòng sửa là **element declaration** đặt bên trong `@interface Flags`, không phải một câu lệnh Java tự do.

### 9.5. Retention của container ngắn hơn annotation chính

```java
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Flags.class)
@interface Flag {}

@Retention(RetentionPolicy.CLASS)
@interface Flags {
    Flag[] value();
}
```

Cấu hình sai: repeated annotation có retention `RUNTIME`, nhưng container chỉ `CLASS`. Compiler yêu cầu retention container phù hợp, không ngắn hơn repeated annotation. Cặp muốn Reflection đọc được nên dùng `RUNTIME` ở cả hai.

### 9.6. @Target không tương thích

Nếu `Flag` được gắn ở parameter, nhưng `Flags` chỉ được phép ở `TYPE`, compiler không thể chứa hợp lệ các lần `@Flag` lặp tại parameter. Cần khai báo target container tương thích với các vị trí cho phép của repeated annotation.

Trong file test đầy đủ, `Tag` và `Tags` đều có `@Target({TYPE, METHOD, PARAMETER})`, nên ba nhóm test class/method/parameter dùng chung một cặp type hợp lệ.

### 9.7. Có @Inherited trên repeated type nhưng thiếu trên container

```java
@Inherited
@Repeatable(Flags.class)
@interface Flag {}

@interface Flags {
    Flag[] value();
}
```

Nếu repeated annotation `Flag` có `@Inherited`, container cũng phải có `@Inherited` theo quy tắc compiler. Ngoài việc sửa cặp khai báo, hãy nhớ `@Inherited` **không** áp dụng để truyền method/parameter annotations theo override.

## 10. Lỗi runtime dễ nhầm với lỗi compiler

### 10.1. getAnnotation(Tag.class) trả null nhưng by-type có giá trị

Tình huống:

```java
@Tag("first")
@Tag("second")
class Pair {}
```

Vì có container, `Pair.class.getDeclaredAnnotation(Tag.class)` trả `null`. Đây là hành vi hợp lệ; không phải compiler bỏ sót `Tag`. Sử dụng `getDeclaredAnnotationsByType(Tag.class)` hoặc đọc trực tiếp `Tags.value()`.

### 10.2. Container rỗng không mang phần tử Tag

`@Tags({})` hoàn toàn có thể tồn tại. `getDeclaredAnnotation(Tags.class)` khác `null`, nhưng `getDeclaredAnnotationsByType(Tag.class).length == 0`. Test consumer phải xét **danh sách thực tế**, không chỉ sự hiện diện của container.

### 10.3. Một Tag trực tiếp có thể không có container

`@Tag("single")` có thể làm `getDeclaredAnnotation(Tags.class)` trả `null`. Nếu consumer chỉ đọc `Tags`, sẽ không nhìn thấy `Tag` trực tiếp. Dùng API by-type để xử lý thống nhất.

### 10.4. Retention SOURCE/CLASS làm Reflection không thấy annotation

Nếu không viết `@Retention`, mặc định là `CLASS`; các API Reflection tiêu chuẩn chỉ thấy annotation phù hợp retention `RUNTIME`. Đặt `@Repeatable` **không tự bật runtime retention**.

Hãy kiểm tra cả hai annotation type: `Tag` và `Tags`. Đổi method Reflection mà không đổi retention sẽ không khiến annotation `CLASS` hiển thị.

### 10.5. Nhầm API declared và associated

`Child.class.getDeclaredAnnotationsByType(Tag.class)` rỗng vì chính `Child` không khai báo `Tag`. Nhưng `Child.class.getAnnotationsByType(Tag.class)` có thể lấy từ `Pair` theo `@Inherited`.

Nếu chỉ muốn metadata trực tiếp để quyết định override, dùng declared API. Nếu muốn metadata theo quy tắc inherited, dùng API associated.

### 10.6. Tưởng @Inherited cộng dồn danh sách cha và con

`ChildOverride` có `@Tag("child")` trực tiếp. `getAnnotationsByType(Tag.class)` trả `[child]` chứ không thêm `first` và `second` từ cha. Nếu cần merge, đó là logic nghiệp vụ phải tự viết và test riêng.

### 10.7. Thứ tự giữa các loại annotation khác nhau

Không nên viết test buộc tất cả annotation có trong `getDeclaredAnnotations()` phải theo thứ tự source giữa các **loại khác nhau**. Thay vào đó, kiểm tra loại đúng rồi so thứ tự mảng các annotation lặp của **cùng một loại**.

### 10.8. Chọn nhầm method hoặc parameter

Method overload dùng chữ ký khác nhau: `getDeclaredMethod("run", String.class)` khác `getDeclaredMethod("run", int.class)`. Đọc method metadata khác với parameter metadata. Nếu test thấy `Tag` có nhưng sai nội dung, hãy xác minh phần tử Reflection đang truy vấn là **đúng declaration**.

## 11. Khi dùng JUnit thay cho test tự viết

Trong dự án có JUnit 5, bạn có thể dùng `assertArrayEquals` để so toàn bộ kết quả thay vì chuỗi. Ví dụ **snippet cần dự án đã cấu hình JUnit Jupiter**:

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import org.junit.jupiter.api.Test;

class RepeatableJUnitTest {
    @Test
    void tagsKeepSourceOrder() {
        Tag[] tags = Pair.class.getDeclaredAnnotationsByType(Tag.class);
        String[] actual = java.util.Arrays.stream(tags)
                .map(Tag::value)
                .toArray(String[]::new);

        assertArrayEquals(
                new String[] {"first", "second"},
                actual);
    }
}
```

Đoạn này **không độc lập chỉ với JDK** vì cần JUnit Jupiter và build/test runner tương ứng; nó tái sử dụng `Tag` và `Pair` từ bài. Bài kiểm thử chính ở mục 4 không cần JUnit, nên chạy được với `javac/java` ngay lập tức.

Nếu sử dụng JUnit, cũng nên có các test đặt tên rõ ràng như `singleTagDoesNotRequireContainer`, `explicitContainerIsExpanded`, `emptyContainerReturnsNoTag` và `inheritedTagDoesNotMergeWithLocalTag`. Mỗi test một ý giúp xác định lỗi nhanh hơn.

## 12. Kiểm thử bằng javap và Java Reflection bổ sung cho nhau

Hai lớp kiểm thử trả lời những câu hỏi khác nhau:

| Công cụ | Kiểm tra gì? | Ví dụ |
| --- | --- | --- |
| `javac` | Source và định nghĩa container có hợp lệ? | Compiler báo lỗi nếu `Tags.value()` sai kiểu |
| `javap -v` | Annotation được mã hóa trong class file thế nào? | `Pair.class` có `Tags` chứa mảng `Tag[]` |
| Java Reflection | API runtime trả metadata ra sao? | `getDeclaredAnnotationsByType(Tag.class)` trả `[first, second]` |
| Bộ assertion/JUnit | Kết quả có đúng hợp đồng mà ứng dụng mong đợi? | Thứ tự, số lượng, tình huống empty/override |
| Test consumer nghiệp vụ | Metadata có được diễn giải đúng trong logic của bạn? | Rule nào chạy trước; dữ liệu trùng được xử lý thế nào |

Một dự án thực tế không nhất thiết dùng cả năm lớp test cho mọi annotation. Nhưng khi đang debug lỗi **container/thứ tự/retention**, kết hợp `javac`, `javap` và Reflection giúp phân loại nguyên nhân nhanh:

- `javac` lỗi: định nghĩa hoặc cách sử dụng annotation không hợp lệ.
- `javac` thành công, `javap` thấy container nhưng Reflection rỗng: nghi retention hoặc hỏi sai API.
- Reflection trả đủ phần tử nhưng consumer xử lý sai thứ tự: lỗi ở consumer hoặc quy tắc nghiệp vụ.
- Chỉ container nhưng bỏ sót single: thiếu nhánh trực tiếp trong code đọc bytecode/metadata.

**Một cảnh báo quan trọng:** nếu build có bước tối ưu/biến đổi bytecode sau `javac`, hãy kiểm tra **class file cuối cùng đang được nạp**, không chỉ class file trung gian. Công cụ bytecode có thể thay đổi metadata tùy cấu hình.

## 13. Bài tập tự kiểm tra

### Bài 1 — Kết quả của từng API

Với `Pair` trong bài, dự đoán:

```java
Pair.class.getDeclaredAnnotation(Tag.class)
Pair.class.getDeclaredAnnotation(Tags.class).value().length
Pair.class.getDeclaredAnnotationsByType(Tag.class).length
```

**Đáp án:** lần lượt `null`, `2`, `2`. `Tag` lặp nằm trong container, API by-type mở container.

### Bài 2 — Kiểm tra thứ tự

Giả sử một consumer vô tình đảo thứ tự thành `[second, first]` nhưng vẫn giữ số phần tử 2. Những test nào sẽ phát hiện?

**Đáp án:** test so **toàn bộ dãy có thứ tự** hoặc so từng index sẽ phát hiện; test chỉ kiểm tra `length == 2` sẽ không phát hiện.

### Bài 3 — Trường hợp single

Tại sao `Single.class.getDeclaredAnnotation(Tags.class)` có thể trả `null` dù `Single.class.getDeclaredAnnotationsByType(Tag.class)` có một phần tử?

**Đáp án:** một `@Tag` duy nhất có thể được biểu diễn trực tiếp, không cần `Tags`.

### Bài 4 — Container tường minh rỗng

Nếu có `@Tags({}) class Empty {}`, có đúng rằng `Empty.class.getDeclaredAnnotation(Tags.class) != null` nhưng `Empty.class.getDeclaredAnnotationsByType(Tag.class).length == 0` không?

**Đáp án:** đúng. Container có mặt, nhưng không chứa annotation `Tag` nào.

### Bài 5 — @Inherited

Nếu `Child extends Pair` không khai báo `Tag`, còn `ChildOverride extends Pair` có `@Tag("child")`, kết quả `getAnnotationsByType(Tag.class)` trên từng lớp là gì?

**Đáp án:** `Child` trả `[first, second]`, `ChildOverride` trả `[child]`. Không có phép nối tự động.

### Bài 6 — Method và parameter

Với `Handler.run` trong bài, muốn đọc `[required, logged]`, bạn lấy `Method` hay `Parameter` làm đối tượng cuối cùng để gọi `getAnnotationsByType(Tag.class)`?

**Đáp án:** lấy `Parameter` ở index 0 từ `run.getParameters()` rồi gọi API trên parameter. Gọi trên `Method` sẽ đọc `[check, audit]`.

### Bài 7 — Sai kiểu chứa

Nếu `Tags` khai báo `String[] value()` thay vì `Tag[] value()`, lỗi xuất hiện ở compile time hay khi gọi Reflection?

**Đáp án:** compile time khi định nghĩa quan hệ `@Repeatable` không hợp lệ, trước khi chạy chương trình.

### Bài 8 — Lỗi retention

Nếu giữ nguyên mã nhưng bỏ `@Retention(RUNTIME)` trên cả `Tag` và `Tags`, Reflection có còn trả `[first, second]` không?

**Đáp án:** không. Retention mặc định là `CLASS`, nên Java Reflection chuẩn không nhìn thấy metadata đó. Công cụ như `javap` vẫn có thể đọc dấu vết `RuntimeInvisibleAnnotations` trong class file.

## 14. Checklist trước khi hoàn tất kiểm thử

1. **Định nghĩa chuẩn:** repeated annotation có `@Repeatable(Container.class)` và container có đúng `Repeated[] value()`?
2. **Metadata nhất quán:** retention, target, `@Inherited` và các phần tử bổ sung của container hợp lệ?
3. **Runtime visibility:** nếu test dùng Reflection, cả hai type được giữ đến runtime?
4. **Test single:** có kiểm tra một annotation trực tiếp mà không cần container?
5. **Test repeated:** có kiểm tra ít nhất hai annotation với **nội dung và thứ tự** cụ thể?
6. **Test explicit container:** consumer đọc được container do người dùng viết trực tiếp?
7. **Test empty container:** tránh nhầm container tồn tại với phần tử bên trong?
8. **Test đúng API:** phân biệt `getAnnotation`/`getDeclaredAnnotation` và các API `...AnnotationsByType`?
9. **Test đúng vị trí:** class, method và parameter được truy vấn đúng `AnnotatedElement`?
10. **Test kế thừa:** chỉ kiểm tra trên class, nhớ `getDeclaredAnnotationsByType` khác `getAnnotationsByType`?
11. **Không tự merge:** khi lớp con có annotation riêng, kết quả có được xác minh là không nối thêm của cha?
12. **Không dựa vào thứ tự thiếu bảo đảm:** chỉ cam kết thứ tự mảng các annotation lặp của cùng loại, không giả định toàn bộ các loại annotation được sắp theo source?
13. **Không phụ thuộc -ea:** test có thực sự chạy assertion khi gọi `java` thường?
14. **Có kiểm tra class file:** dùng `javap -v` để phân biệt lỗi biểu diễn container với lỗi API runtime?
15. **Có output xác định:** khi thất bại, test chỉ rõ trường hợp nào, expected là gì và actual là gì?

**Kết luận:** kiểm thử annotation lặp phải nhìn đồng thời vào **kiểu chứa, API truy vấn và thứ tự các phần tử trong mảng**. Một phép thử chỉ đếm số annotation không thể phát hiện đảo thứ tự; một phép thử chỉ lấy container bỏ sót annotation đơn; và một phép thử chỉ dùng `getAnnotation` bỏ sót danh sách annotation lặp. Bộ test tự chạy trên JDK 17+, kết hợp `getDeclaredAnnotationsByType` với `javap -v`, giúp kiểm tra đúng hành vi Java cốt lõi và xác định rõ lỗi nằm ở compile-time, runtime visibility hay logic tiêu thụ metadata.