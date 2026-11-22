# Annotation trên kiểu phần tử và từng chiều của mảng trong Java

Một mảng Java có thể mang metadata không chỉ tại khai báo biến, mà còn tại **từng tầng của kiểu mảng**. Với kiểu `String[][]`, có ba vị trí type-use cần phân biệt: **kiểu phần tử `String`**, **mảng hai chiều `String[][]`** và **mảng một chiều `String[]` nằm bên trong nó**. Từ Java 8, annotation có `@Target(ElementType.TYPE_USE)` có thể đánh dấu riêng từng vị trí này.

Đây là một trường hợp quan trọng của *type annotation*: cách đặt annotation **trước tên kiểu** và **trước từng cặp dấu `[]`** mang ý nghĩa khác nhau. Đặc biệt, annotation ở ngay trước `String` không tự động có nghĩa là “toàn bộ mảng `String[][]` được annotate”.

## 1. Vì sao cần phân biệt kiểu phần tử và từng chiều của mảng?

Xét biến:

```java
String[][] matrix;
```

Có thể đọc kiểu này theo ba tầng:

```text
matrix
  └─ String[][]        ← Kiểu của matrix: mảng ngoài (2 chiều)
       └─ String[]      ← Kiểu của mỗi phần tử trong mảng ngoài: mảng trong
            └─ String   ← Kiểu phần tử ở tầng cuối
```

Một reference kiểu `String[][]` có thể trỏ đến mảng ngoài; mỗi phần tử của mảng ngoài là một reference kiểu `String[]`; mỗi phần tử của mảng trong là reference kiểu `String`. Đây là **ba vị trí kiểu khác nhau** mà công cụ phân tích tĩnh có thể cần phân biệt.

Giả sử một thư viện kiểm tra nullness muốn mô tả:

- Tham chiếu tới **mảng ngoài** không được `null`.
- Mỗi **mảng con** (hàng) không được `null`.
- Các **chuỗi** trong mỗi hàng không được `null`.

Đó là ba yêu cầu độc lập. Java không tự thực thi những quy tắc ấy chỉ vì code có annotation; một checker hoặc thư viện phải hiểu và áp dụng metadata tương ứng. Nhưng cú pháp ngôn ngữ cho phép ta gắn dấu ở đúng từng vị trí để checker có thông tin chính xác.

Đối với mảng một chiều `String[]`, chỉ có hai tầng cần phân biệt: `String[]` và `String`.

## 2. Cú pháp chuẩn: annotation đặt ngay trước thành phần kiểu được đánh dấu

Giả sử ba kiểu annotation `@ElementMark`, `@OuterMark`, `@InnerMark` đều có `@Target(ElementType.TYPE_USE)`. Đoạn sau minh họa **vị trí đặt annotation**:

```java
@ElementMark String @OuterMark [] @InnerMark [] matrix;
```

Cách đọc chuẩn:

| Thành phần cú pháp | Kiểu được đánh dấu | Ý nghĩa vị trí |
| --- | --- | --- |
| `@ElementMark String` | `String` | Kiểu phần tử cuối cùng. |
| `@OuterMark []` (dấu `[]` thứ nhất) | `String[][]` | Kiểu của **mảng ngoài**. |
| `@InnerMark []` (dấu `[]` thứ hai) | `String[]` | Kiểu **mảng con**, là component type của mảng ngoài. |

Quy tắc của Java Language Specification là: **annotation đứng trước cặp dấu `[]` nào thì gắn vào mức kiểu mảng do cặp dấu đó biểu diễn**. Trong cú pháp thông thường với các cặp ngoặc ở phía sau tên kiểu, cặp thứ nhất tính từ trái qua phải tương ứng mảng ngoài cùng.

Có thể so sánh bốn khai báo (đây là các đoạn minh họa, giả sử annotation có mục tiêu `TYPE_USE`):

```java
@ElementMark String[][] a;        // Đánh dấu kiểu phần tử String
String @OuterMark [][] b;         // Đánh dấu mảng ngoài String[][]
String[] @InnerMark [] c;         // Đánh dấu mảng con String[]
@ElementMark String @OuterMark [] @InnerMark [] d; // Đánh dấu cả ba tầng
```

**Đừng suy đoán vị trí từ tên annotation.** Một annotation đặt tên là `@NonNull` nhưng nằm trước `String` đánh dấu **kiểu phần tử**; nếu đặt trước cặp `[]` đầu tiên, nó đánh dấu **kiểu mảng ngoài**. Hành vi kiểm tra null thực tế vẫn do công cụ sử dụng annotation quyết định.

## 3. Khai báo type annotation hợp lệ

Để dùng annotation ở các vị trí bên trong kiểu mảng, định nghĩa kiểu annotation với `ElementType.TYPE_USE`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface ElementLabel {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface DimensionLabel {
    String value();
}
```

Ở đây:

- `@Target(TYPE_USE)` cấp phép đặt annotation trên nơi sử dụng một kiểu, bao gồm kiểu phần tử và mỗi tầng mảng.
- `@Retention(RUNTIME)` giữ metadata trong class file và cho phép một phần của Java Reflection đọc tại runtime.
- `value()` là element của annotation để lưu chuỗi mô tả; giá trị `"outer"`, `"inner"`, `"cell"` chỉ dùng phục vụ minh họa, không được Java diễn giải thành quy tắc có sẵn.

Nếu đổi thành `@Target(ElementType.FIELD)` đơn thuần, annotation sẽ nhắm vào **khai báo field**, không đủ điều kiện để viết tại các dấu `[]` hay để chú thích kiểu phần tử. Muốn hỗ trợ cả hai mục đích, có thể khai báo `@Target({ElementType.FIELD, ElementType.TYPE_USE})`, nhưng phải hiểu hai ngữ cảnh độc lập.

Annotation không khai báo retention thì mặc định là `CLASS`; phản chiếu type annotation qua runtime trong ví dụ dưới cần `RUNTIME`.

## 4. Ví dụ Java 17+ hoàn chỉnh, đọc riêng ba tầng bằng Reflection

Tạo file đúng tên **`ArrayTypeAnnotationDemo.java`**, đặt toàn bộ code sau vào file:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface ElementLabel {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface DimensionLabel {
    String value();
}

class DataGrid {
    @ElementLabel("cell")
    String @DimensionLabel("outer") [] @DimensionLabel("inner") [] cells;
}

public class ArrayTypeAnnotationDemo {
    public static void main(String[] args) throws Exception {
        Field field = DataGrid.class.getDeclaredField("cells");

        AnnotatedType outer = field.getAnnotatedType();
        AnnotatedType inner =
                ((AnnotatedArrayType) outer).getAnnotatedGenericComponentType();
        AnnotatedType element =
                ((AnnotatedArrayType) inner).getAnnotatedGenericComponentType();

        System.out.println("type=" + field.getType().getTypeName());
        System.out.println("outer=" +
                outer.getAnnotation(DimensionLabel.class).value());
        System.out.println("inner=" +
                inner.getAnnotation(DimensionLabel.class).value());
        System.out.println("element=" +
                element.getAnnotation(ElementLabel.class).value());
        System.out.println("allocated=" + (new String[2][3]).length);
    }
}
```

Chạy trong thư mục chứa file với JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 ArrayTypeAnnotationDemo.java
java ArrayTypeAnnotationDemo
```

**Stdout chính xác:**

```text
type=java.lang.String[][]
outer=outer
inner=inner
element=cell
allocated=2
```

Ví dụ này đã được kiểm tra biên dịch và chạy bằng JDK 21, và chỉ sử dụng tính năng có trong Java 17.

### Vì sao kết quả hiển thị như vậy?

1. `DataGrid.cells` có kiểu Java cơ bản `String[][]`. Việc gắn annotation ở các tầng kiểu **không biến nó thành kiểu mảng mới**, vì thế `field.getType().getTypeName()` vẫn là `"java.lang.String[][]"`.
2. `field.getAnnotatedType()` trả về `AnnotatedType` đại diện **kiểu ngoài cùng**, tức `String[][]` được đánh dấu `@DimensionLabel("outer")`.
3. Vì đây là mảng, đối tượng đó có thể được xem là `AnnotatedArrayType`. Gọi `getAnnotatedGenericComponentType()` một lần đi xuống **một tầng** đến kiểu `String[]`, nơi chứa `@DimensionLabel("inner")`.
4. Gọi tiếp lần nữa đi đến kiểu **`String`**, nơi chứa `@ElementLabel("cell")`.
5. `getAnnotation(DimensionLabel.class)` hoặc `getAnnotation(ElementLabel.class)` được gọi trên **đúng đối tượng `AnnotatedType` của từng tầng**; đó là lý do cùng một kiểu annotation `DimensionLabel` nhưng lấy ra hai giá trị khác nhau.
6. `new String[2][3]` cấp phát một mảng ngoài có chiều dài `2` (hai hàng), mỗi hàng dài `3`. Type annotation trên field không thay đổi cách cấp phát hay độ dài, và biểu thức này không tự kế thừa metadata từ field.

**Quan trọng:** `Field.getAnnotations()` nhằm truy xuất annotation của **khai báo field**; nó không thay thế `Field.getAnnotatedType()` khi cần biết annotation nằm ở kiểu phần tử hoặc từng tầng `[]`. Với bài toán này phải truy cập **cấu trúc kiểu được annotate**.

## 5. Phân biệt mảng ngoài, mảng trong và phần tử cuối

Ví dụ:

```java
String @DimensionLabel("outer") [] @DimensionLabel("inner") [] matrix;
```

`matrix` có kiểu `String[][]`. Nếu giả sử có một checker hiểu ý nghĩa annotation:

- `@DimensionLabel("outer")` gắn vào kiểu `String[][]`, kiểu của **biến `matrix`**.
- `@DimensionLabel("inner")` gắn vào kiểu `String[]`, kiểu của **`matrix[i]`**.
- Nếu đặt thêm `@ElementLabel("cell")` ngay trước `String`, annotation ấy gắn vào kiểu của **`matrix[i][j]`**.

Bản thân `DimensionLabel` và `ElementLabel` ở ví dụ chỉ lưu text; Java không dùng `"outer"` hoặc `"inner"` để cấm giá trị null. Vị trí annotate và khả năng kiểm chứng là hai câu chuyện khác nhau.

Với mảng **ba chiều**:

```java
String @DimensionLabel("3D") []
       @DimensionLabel("2D") []
       @DimensionLabel("1D") [] cube;
```

Từ trái sang phải, ba cặp `[]` tương ứng ba mức `String[][][]`, `String[][]` và `String[]`. Annotation trước tên `String`, nếu có, vẫn nhắm vào **kiểu phần tử `String` cuối cùng**.

Có thể đọc mỗi mức bằng cách lặp `AnnotatedArrayType.getAnnotatedGenericComponentType()` cho đến khi gặp `AnnotatedType` không còn là mảng. Nếu type chỉ có một chiều, có đúng **một** lần đi xuống để từ kiểu mảng tới kiểu phần tử.

## 6. Annotation trên biểu thức tạo mảng

Type annotation cũng có thể xuất hiện trong **biểu thức tạo mảng**, trước từng kích thước, với cú pháp hơi khác khai báo biến:

```java
String @DimensionLabel("outer") [] @DimensionLabel("inner") [] data =
        new String @DimensionLabel("outer") [2]
                   @DimensionLabel("inner") [3];
```

Ở vế trái, `[]` khai báo các tầng kiểu mảng; ở vế phải, `[2]` và `[3]` thực hiện cấp phát từng chiều. Annotation đứng **ngay trước dấu `[`** của chiều tương ứng.

Nếu cần chú thích kiểu phần tử trong biểu thức tạo mảng:

```java
@ElementLabel("cell")
String @DimensionLabel("outer") [] @DimensionLabel("inner") [] data =
        new @ElementLabel("cell")
            String @DimensionLabel("outer") [2]
                   @DimensionLabel("inner") [3];
```

Đây là những đoạn minh họa cú pháp độc lập; chúng giả định `ElementLabel` và `DimensionLabel` được khai báo như ở mục 3. Khai báo biến và biểu thức `new` là **hai ngữ cảnh type-use riêng**. Java không tự sao chép một type annotation từ khai báo sang biểu thức tạo mảng; viết annotation ở vế nào là lựa chọn của mã nguồn tại vế đó.

Khi tạo mảng nhiều chiều không đầy đủ, như `new String[2][]`, chỉ chiều ngoài được cấp phát; các mảng trong ở mỗi ô ban đầu là `null`. Một marker type-use không tự làm cho các mảng bên trong được tạo hay trở thành non-null.

## 7. Type annotation và declaration annotation: cùng dấu `@`, khác vị trí

So sánh hai ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface FieldMarker {
}

@Target(ElementType.TYPE_USE)
@interface TypeMarker {
}

class Holder {
    @FieldMarker
    String[] first;

    String @TypeMarker [] second;

    @TypeMarker
    String[] third;
}
```

- `@FieldMarker` nằm trước field và có `@Target(FIELD)`: nó ghi dấu lên **khai báo field**.
- `String @TypeMarker [] second` ghi dấu lên **kiểu mảng `String[]`** của field `second`.
- `@TypeMarker String[] third` ghi dấu lên **kiểu phần tử `String`** của mảng `third` (vì annotation type chỉ có `TYPE_USE`).

Vị trí cú pháp trước tên kiểu có thể được coi là ngữ cảnh khai báo hoặc kiểu tùy `@Target` của annotation, nên **đừng chỉ nhìn khoảng trắng** để xác định ý nghĩa. Căn cứ quan trọng là target hợp lệ và vị trí ngay trước dấu ngoặc chiều mảng.

Ví dụ `@TypeMarker` ở đây không tự yêu cầu một biến phải có giá trị, không tự thêm kiểm tra null và không tự thay đổi JVM type. Nó đơn thuần gắn metadata lên nơi sử dụng kiểu.

## 8. Những nhầm lẫn liên quan mảng có nhiều giá trị

Một kiểu annotation có element kiểu mảng là chuyện **khác** với annotation của **kiểu mảng**.

```java
@interface Tags {
    String[] value();
}

@Tags({"a", "b"})
class Sample {
}
```

Trong trường hợp này, `Tags.value()` trả về `String[]` chứa hai chuỗi. `@Tags` đang được đặt trên **khai báo class** (annotation này không chỉ rõ target, nên mặc định áp dụng được ở các declaration context phù hợp), và **không** có ý nghĩa annotate chiều mảng.

Ngược lại:

```java
class TypeUseSample {
    String @DimensionLabel("outer") [] names;
}
```

`@DimensionLabel` được đặt tại **kiểu mảng** của field `names`. Nó không bắt buộc `DimensionLabel` phải có element kiểu mảng; trong ví dụ element `value()` chỉ là một chuỗi.

Cũng đừng đánh đồng type annotation với kích thước mảng: `String @DimensionLabel("outer") []` **không chứa số `2` hay `3`**, vì độ dài mảng là thông tin runtime của object. `@DimensionLabel("outer")` chỉ nói annotation này gắn vào **tầng kiểu** nào.

## 9. Một số điểm cần chú ý khi kết hợp nhiều dấu `[]`

### Các kiểu khai báo có dấu ngoặc sau tên biến

Java vẫn cho phép cú pháp lịch sử:

```java
String[] first, second[];
```

Trong đó `first` là `String[]`, còn `second` là `String[][]`. Tuy nhiên, khi có type annotations gắn lên các tầng mảng, cú pháp trộn ngoặc sau tên kiểu và sau tên biến rất dễ gây nhầm về thứ tự các chiều.

Theo Java Language Specification, thứ tự annotation được xác định theo cách ghép các cặp ngoặc của kiểu cho **từng biến**, không phải chỉ đọc tuần tự toàn bộ dòng một cách tùy ý. Vì vậy trong code cần annotate nhiều chiều, nên viết từng khai báo rõ ràng, đặt toàn bộ dấu ngoặc ở bên phải **tên kiểu**:

```java
String @DimensionLabel("outer") [] first;
String @DimensionLabel("outer") [] @DimensionLabel("inner") [] second;
```

Đây là khuyến nghị về tính dễ đọc; Java vẫn cho phép cú pháp khai báo mảng kế thừa từ C.

### Array type được annotate không thay đổi tính tương thích kiểu

```java
String @DimensionLabel("outer") [] first;
String[] second;

second = first;
```

Theo **hệ thống kiểu Java chuẩn**, hai biến đều là `String[]` và phép gán hợp lệ; annotation này không tự tạo một subtype mới. Một công cụ kiểm tra bổ sung có thể đưa ra cảnh báo hoặc lỗi riêng tùy theo ý nghĩa và cấu hình mà nó quy ước cho `DimensionLabel`.

Không nên suy diễn rằng `String @NonNull []` được Java compiler kiểm tra chống `null` khi chưa có checker phù hợp. Nhiều hệ sinh thái như Checker Framework cung cấp annotation và công cụ xử lý theo hợp đồng của riêng chúng; đó là tầng kiểm tra bổ sung bên trên cú pháp Java.

### Reflection chỉ thấy retention và vị trí đã giữ lại

Nếu annotation khai báo `@Retention(SOURCE)`, annotation có thể hữu ích cho công cụ đọc source nhưng **không còn trong class file** để Reflection runtime truy xuất. Với retention `CLASS`, thông tin có thể hiện diện trong class file nhưng Java Reflection thông thường không phơi bày như `RUNTIME`. Ví dụ chính dùng `RUNTIME` để cho phép đọc từng tầng bằng `AnnotatedType`.

Với khai báo biến cục bộ (*local variable*), Java Reflection không có API tương tự `Field.getAnnotatedType()` để liệt kê mọi type annotation của local variable trong một phương thức. Đoạn mã chạy được cố ý sử dụng **field** để minh họa một cách đọc runtime rõ ràng.

## 10. Các lỗi phổ biến

| Lỗi hoặc hiểu sai | Cách hiểu đúng |
| --- | --- |
| Viết `@ElementMark String[][]` và nghĩ marker gắn lên cả mảng 2 chiều | Marker trước `String` thuộc **kiểu phần tử**. Gắn trước `[]` đầu tiên để đánh dấu mảng ngoài. |
| Viết `String @OuterMark [] @InnerMark []` rồi gọi cả hai là annotation của `String` | Marker thứ nhất thuộc `String[][]`; marker thứ hai thuộc `String[]`. |
| Định nghĩa annotation với chỉ `@Target(FIELD)` rồi đặt giữa `String` và `[]` | Dùng `@Target(TYPE_USE)` để đặt ở tầng kiểu mảng. |
| Dùng `Field.getAnnotations()` để đọc annotation trên chiều mảng | Dùng `Field.getAnnotatedType()`, rồi đi xuống các mức `AnnotatedArrayType`. |
| Dùng `@Retention(SOURCE)` mà chờ Reflection runtime đọc được | Chọn `RUNTIME` nếu cần truy cập qua Reflection. |
| Cho rằng annotation làm Java tự cấm null hoặc đổi kích thước mảng | Annotation không tự biến đổi hành vi runtime hay kích thước mảng. |
| Lẫn `String[] value()` trong khai báo annotation với `String @A []` | Một bên là **kiểu của element annotation**, bên kia là **annotation gắn vào một kiểu mảng**. |
| Nghĩ mọi dấu `[]` trong `String[][]` cùng chỉ một kiểu | Mỗi cặp `[]` tạo ra một tầng kiểu mảng có component type riêng. |

## 11. Tự kiểm tra

Giả sử `@A`, `@B` và `@C` đều có `@Target(TYPE_USE)`, xét khai báo:

```java
@C String @A [] @B [] names;
```

1. `@A` gắn lên kiểu nào? **`String[][]`**, tức mảng ngoài.
2. `@B` gắn lên kiểu nào? **`String[]`**, tức kiểu của mỗi mảng con.
3. `@C` gắn lên kiểu nào? **`String`**, tức kiểu phần tử cuối.
4. Nếu chỉ viết `@C String[][] names;`, `@C` có tự áp dụng lên mọi tầng không? **Không**: vị trí của nó vẫn là kiểu phần tử `String`.
5. Nếu khai báo `String @A [] @B [] names;` mà `@B` chỉ có `@Target(FIELD)`, có biên dịch được không? **Không**: nơi đứng trước dấu `[]` là ngữ cảnh type-use, không phải khai báo field.
6. Nếu cần đọc `@B` ở runtime từ một field, có thể lấy trực tiếp `field.getAnnotation(B.class)` không? **Không phù hợp**: cần lấy `field.getAnnotatedType()` rồi lấy `getAnnotatedGenericComponentType()` của mảng ngoài trước.

Tài liệu tham khảo chính thức: [Java Language Specification 21 – §9.7.4 Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.4) và [§10.1 Array Types, §10.2 Array Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-10.html). Hai phần này quy định chính xác annotation trên **kiểu phần tử** và trên **mỗi chiều mảng**, bao gồm thứ tự các cặp dấu ngoặc.
