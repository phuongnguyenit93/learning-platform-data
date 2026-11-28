# Khớp với class, interface, subtype và array reference

## 1. Cách `instanceof` xác định một kiểu có khớp hay không

Type pattern của `instanceof` kiểm tra kiểu tham chiếu thực tế của đối tượng tại thời điểm chạy. Kiểu được ghi trong pattern có thể là một lớp, giao diện hoặc kiểu mảng. Nếu đối tượng khớp, pattern variable được ràng buộc với chính đối tượng đó dưới kiểu tĩnh đã khai báo.

Ví dụ:

~~~java
Object candidate = "Java";

if (candidate instanceof String text) {
    System.out.println(text.toUpperCase());
}
~~~

`candidate` có kiểu tĩnh `Object`, còn đối tượng thực tế là `String`. Phép kiểm tra khớp và biến `text` có kiểu tĩnh `String`.

Tính năng pattern matching for `instanceof` là cú pháp chính thức từ Java 16 (JEP 394). Các quy tắc khớp theo lớp, giao diện và mảng dưới đây là quy tắc kiểu tham chiếu của Java, tiếp tục được áp dụng trong các phiên bản hiện đại.

## 2. Khớp với class và các lớp con

### 2.1. Pattern kiểu lớp cha nhận cả đối tượng của lớp con

Giả sử có một hệ thống tài liệu:

~~~java
abstract class Document {
    String title;
}

final class Invoice extends Document {
    int invoiceNumber;
}
~~~

Một đối tượng `Invoice` cũng là một `Document`, vì `Invoice` kế thừa `Document`:

~~~java
Object candidate = new Invoice();

if (candidate instanceof Document document) {
    System.out.println("Đây là tài liệu");
}
~~~

Pattern `Document document` khớp với đối tượng `Invoice`. Biến `document` có kiểu tĩnh `Document`, không tự động mang kiểu `Invoice` chỉ vì lớp thực tế của đối tượng là `Invoice`.

Nếu cần thành viên riêng của lớp con, kiểm tra bằng pattern cụ thể hơn:

~~~java
if (candidate instanceof Invoice invoice) {
    System.out.println(invoice.invoiceNumber);
}
~~~

Như vậy, một pattern kiểu lớp cha thường dùng để xử lý hành vi chung; pattern kiểu lớp con dùng khi thật sự cần hành vi riêng của lớp đó.

### 2.2. Phân nhánh theo các subtype

Khi cần xử lý một số subtype theo cách khác nhau, có thể đặt các pattern cụ thể trước pattern tổng quát:

~~~java
static String describe(Object candidate) {
    if (candidate instanceof Invoice invoice) {
        return "Hóa đơn số " + invoice.invoiceNumber;
    }
    if (candidate instanceof Document document) {
        return "Tài liệu: " + document.title;
    }
    return "Đối tượng khác";
}
~~~

Nếu đặt nhánh `Document` trước, một `Invoice` cũng khớp ngay với nhánh đó và không đi đến nhánh `Invoice`. Vì vậy, khi phân nhánh theo cây kế thừa, hãy xử lý subtype cụ thể trước, rồi mới đến kiểu cha tổng quát.

### 2.3. `instanceof` không yêu cầu lớp thực tế trùng khít

`candidate instanceof Document document` có nghĩa là đối tượng có thể gán cho kiểu `Document`, bao gồm cả instance của lớp con. Nó không phải phép so sánh lớp thực tế để đòi hỏi đối tượng có đúng class `Document`.

Nếu nghiệp vụ thật sự yêu cầu đúng lớp runtime, có thể so sánh `getClass()` sau khi đã xử lý `null`:

~~~java
Object candidate = new Invoice();

if (candidate != null && candidate.getClass() == Invoice.class) {
    System.out.println("Đúng chính xác lớp Invoice");
}
~~~

So sánh `getClass()` là một yêu cầu khác với kiểm tra subtype. Trong thiết kế hướng đối tượng, nên ưu tiên `instanceof` khi muốn chấp nhận các lớp con và tận dụng đa hình.

## 3. Khớp với interface và các lớp triển khai

### 3.1. Đối tượng khớp với interface mà lớp triển khai

Một pattern có thể khai báo kiểu là giao diện. Đối tượng khớp nếu lớp thực tế triển khai giao diện đó, trực tiếp hoặc thông qua lớp cha:

~~~java
interface Exportable {
    void export();
}

class Report implements Exportable {
    @Override
    public void export() {
        System.out.println("Export report");
    }
}

class ArchivedReport extends Report {
}
~~~

Sử dụng:

~~~java
Object candidate = new ArchivedReport();

if (candidate instanceof Exportable exportable) {
    exportable.export();
}
~~~

`ArchivedReport` kế thừa `Report`, còn `Report` triển khai `Exportable`. Do đó, đối tượng `ArchivedReport` cũng khớp với pattern `Exportable exportable`. Biến `exportable` có kiểu tĩnh là `Exportable`, nên chỉ gọi được các thành viên được khai báo trong giao diện.

### 3.2. Khớp với giao diện cha của một giao diện con

Giao diện cũng có quan hệ kế thừa:

~~~java
interface Resource {
}

interface ReadableResource extends Resource {
    String read();
}

class FileResource implements ReadableResource {
    @Override
    public String read() {
        return "Nội dung tệp";
    }
}
~~~

Một `FileResource` có thể khớp với cả hai pattern:

~~~java
Object candidate = new FileResource();

if (candidate instanceof Resource resource) {
    System.out.println("Là một resource");
}

if (candidate instanceof ReadableResource readable) {
    System.out.println(readable.read());
}
~~~

`ReadableResource` là subtype của `Resource`, nên một đối tượng triển khai `ReadableResource` cũng có thể được xem là `Resource`. Kiểu tĩnh của mỗi pattern variable vẫn là kiểu được ghi trong pattern tương ứng.

### 3.3. Một lớp có thể triển khai nhiều interface

Các interface không có quan hệ kế thừa trực tiếp vẫn có thể cùng khớp với một đối tượng nếu lớp của đối tượng triển khai cả hai:

~~~java
interface Printable {
}

interface Auditable {
    void audit();
}

class ReportDocument implements Printable, Auditable {
    @Override
    public void audit() {
        System.out.println("Audit report");
    }
}
~~~

~~~java
Object candidate = new ReportDocument();

if (candidate instanceof Printable printable) {
    System.out.println("Có thể in");
}

if (candidate instanceof Auditable auditable) {
    auditable.audit();
}
~~~

Đừng kết luận hai interface không thể khớp chỉ vì chúng không kế thừa lẫn nhau. Một lớp có thể triển khai đồng thời nhiều giao diện, nên cùng một đối tượng có thể thỏa mãn nhiều type pattern.

### 3.4. Khi nào kiểu class và interface không thể khớp?

Khả năng khớp còn phụ thuộc vào kiểu tĩnh của biểu thức nguồn và quan hệ kiểu hợp lệ. Nếu kiểu nguồn là một lớp `final` không triển khai một interface nào đó, không thể có lớp con nào mở rộng lớp đó để bổ sung interface:

~~~java
final class FixedValue {
}

interface RunnableTask {
}

FixedValue candidate = new FixedValue();

// Không hợp lệ: FixedValue là final và không triển khai RunnableTask.
// if (candidate instanceof RunnableTask task) {
//     ...
// }
~~~

Ngược lại, nếu kiểu nguồn là một lớp không `final`, một lớp con có thể triển khai thêm interface; phép kiểm tra có thể hợp lệ nếu các quy tắc chuyển đổi kiểu của Java cho phép khả năng đó. Vì vậy, cần xem xét cả kiểu tĩnh, quan hệ kế thừa và việc lớp có thể được mở rộng hay không.

## 4. Khớp với array reference

Mảng trong Java là đối tượng. Vì vậy, một biểu thức kiểu `Object` có thể được kiểm tra bằng pattern mang kiểu mảng:

~~~java
Object candidate = new String[] { "Java", "16" };

if (candidate instanceof String[] words) {
    System.out.println(words.length);
    System.out.println(words[0]);
}
~~~

Biến `words` có kiểu tĩnh `String[]`. Sau khi khớp, có thể truy cập độ dài, phần tử và các thao tác dành cho mảng chuỗi.

### 4.1. Mảng tham chiếu có tính đồng biến (*array covariance*)

Java cho phép mảng của kiểu tham chiếu có thể gán cho mảng của kiểu cha tương ứng. Chẳng hạn, `String[]` là subtype của `Object[]`:

~~~java
Object candidate = new String[] { "A", "B" };

if (candidate instanceof Object[] elements) {
    System.out.println(elements[0]);
}
~~~

Pattern `Object[] elements` khớp với một đối tượng `String[]`, vì mọi phần tử `String` cũng là `Object`. Biến `elements` có kiểu tĩnh `Object[]`, dù kiểu runtime của mảng vẫn là `String[]`.

Tính đồng biến của mảng có một hệ quả cần chú ý:

~~~java
Object candidate = new String[] { "A", "B" };

if (candidate instanceof Object[] elements) {
    elements[0] = "Java"; // Hợp lệ
    // elements[1] = 16;  // Biên dịch được nhưng ném ArrayStoreException
}
~~~

Phép kiểm tra pattern xác nhận đối tượng là một `Object[]` theo quan hệ subtype, nhưng không biến mảng `String[]` thực tế thành mảng có thể chứa mọi loại `Object`. JVM vẫn kiểm tra kiểu phần tử lúc ghi; nếu ghi một `Integer` vào mảng `String[]`, thao tác ném `ArrayStoreException`.

### 4.2. Mảng kiểu nguyên thủy không phải `Object[]`

Mảng có phần tử kiểu nguyên thủy vẫn là đối tượng, nhưng `int[]` không phải subtype của `Object[]`:

~~~java
Object candidate = new int[] { 10, 20, 30 };

if (candidate instanceof int[] numbers) {
    System.out.println(numbers[0]);
}

// Không khớp: int[] không phải Object[].
if (candidate instanceof Object[] objects) {
    // Không được thực thi.
}
~~~

`int` là kiểu nguyên thủy, không phải kiểu tham chiếu con của `Object`. Vì vậy, mảng `int[]` không thể được xem là `Object[]`. Đây là điểm khác với `String[]`, vì `String` là kiểu tham chiếu.

Nếu cần xử lý chung một mảng bất kỳ, có thể kiểm tra kiểu `Object` hoặc các interface mà mọi mảng triển khai, thay vì giả định mọi mảng đều là `Object[]`.

### 4.3. Mảng nhiều chiều là mảng của các mảng

Mảng nhiều chiều trong Java thực chất là mảng mà mỗi phần tử có thể là một mảng khác:

~~~java
Object matrix = new int[][] {
    { 1, 2 },
    { 3, 4 }
};

if (matrix instanceof Object[] rows) {
    System.out.println(rows.length);
    if (rows[0] instanceof int[] firstRow) {
        System.out.println(firstRow[0]);
    }
}
~~~

`int[][]` là một mảng có phần tử kiểu `int[]`. Mỗi `int[]` là một đối tượng, nên `int[][]` có thể khớp với `Object[]`. Tuy nhiên, `int[][]` không phải `Object[][]`, bởi `int[]` không phải subtype của `Object[]`.

Với mảng chuỗi hai chiều, quan hệ khác đi:

~~~java
Object matrix = new String[][] {
    { "A", "B" },
    { "C" }
};

if (matrix instanceof Object[][] rows) {
    System.out.println(rows[0][0]);
}
~~~

`String[][]` có thể khớp với `Object[][]`, vì `String[]` là subtype của `Object[]`.

### 4.4. Mọi array đều là Object và triển khai Cloneable, Serializable

Trong Java, tất cả kiểu mảng đều là kiểu tham chiếu con của `Object` và triển khai hai interface đánh dấu `Cloneable` và `java.io.Serializable`. Điều này đúng cả với mảng kiểu nguyên thủy:

~~~java
Object candidate = new int[] { 1, 2, 3 };

if (candidate instanceof Cloneable cloneable) {
    System.out.println("Mảng hỗ trợ clone");
}

if (candidate instanceof java.io.Serializable serializable) {
    System.out.println("Mảng có thể được serialize theo cơ chế Java");
}
~~~

Các pattern trên kiểm tra interface mà đối tượng mảng triển khai. Chúng không có nghĩa là `int[]` có thể khớp với `Object[]`; hai quan hệ kiểu này khác nhau.

## 5. Tổng hợp quan hệ khớp

| Kiểu đối tượng thực tế | Pattern | Kết quả |
| --- | --- | --- |
| `Invoice` kế thừa `Document` | `Document document` | Khớp |
| `ArchivedReport` kế thừa lớp triển khai `Exportable` | `Exportable exportable` | Khớp |
| `FileResource` triển khai `ReadableResource`, giao diện này mở rộng `Resource` | `Resource resource` | Khớp |
| `ReportDocument` triển khai hai interface | `Printable printable` hoặc `Auditable auditable` | Cả hai đều khớp |
| `String[]` | `Object[] elements` | Khớp nhờ array covariance |
| `int[]` | `Object[] elements` | Không khớp |
| `int[][]` | `Object[] rows` | Khớp |
| `int[][]` | `Object[][] rows` | Không khớp |
| Bất kỳ mảng nào | `Cloneable value` | Khớp |

## 6. Cách chọn pattern phù hợp

- Dùng pattern lớp cha khi muốn xử lý mọi subtype theo hành vi chung.
- Dùng pattern lớp con khi cần thành viên hoặc hành vi riêng của subtype đó; đặt nhánh cụ thể trước nhánh tổng quát.
- Dùng pattern interface khi chỉ quan tâm đến khả năng/hợp đồng mà đối tượng cung cấp, kể cả khi nhiều lớp không cùng một nhánh kế thừa.
- Dùng pattern mảng cụ thể như `String[]` hoặc `int[]` khi cần làm việc với phần tử theo đúng kiểu.
- Chỉ dùng `Object[]` khi chấp nhận mọi mảng có phần tử là kiểu tham chiếu; mảng kiểu nguyên thủy một chiều như `int[]` không khớp.
- Nhớ rằng array covariance có thể dẫn đến `ArrayStoreException` khi ghi phần tử sai kiểu runtime.

**Ghi nhớ:** type pattern khớp theo quan hệ kiểu của đối tượng, không đòi hỏi tên lớp runtime phải trùng với kiểu pattern. Quan hệ kế thừa, triển khai interface và quy tắc subtype của mảng quyết định phép khớp; kiểu được khai báo trong pattern quyết định các thành viên mà pattern variable có thể sử dụng.
