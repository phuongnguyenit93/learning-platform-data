# Dấu gạch dưới đơn lẻ không dùng làm tên định danh thông thường trong Java

## Mục tiêu

Trong Java, dấu gạch dưới (underscore, ký hiệu `_`) có thể xuất hiện trong tên biến, tên phương thức, tên lớp và trong một số cú pháp ngôn ngữ. Tuy nhiên, một dấu gạch dưới đứng riêng không phải là tên định danh thông thường.

Từ Java 9, `_` là từ khóa dành riêng nên không thể dùng làm tên biến, tham số, phương thức, lớp hoặc thành phần định danh thông thường. Từ Java 22, Java chuẩn hóa thêm **unnamed variables** và **unnamed patterns**: dấu `_` được dùng trong một số vị trí cú pháp để biểu thị giá trị có chủ ý không sử dụng. Cách dùng mới này không biến `_` thành một tên định danh có thể tham chiếu.

## 1. Định danh trong Java là gì?

Định danh (identifier) là tên dùng để đặt cho các thành phần như:

- Biến cục bộ, biến instance và biến static.
- Tham số phương thức, constructor hoặc lambda.
- Lớp, interface, enum và record.
- Phương thức, constructor và trường dữ liệu.
- Package và các thành phần khác được đặt tên trong chương trình.

Định danh giúp chương trình tham chiếu đến đúng thành phần trong phạm vi cho phép. Ví dụ:

~~~java
int totalCount = 10;
String user_name = "Lan";

class OrderService {
    void processOrder() {
        System.out.println(user_name);
    }
}
~~~

Các tên `totalCount`, `user_name`, `OrderService` và `processOrder` là những định danh có ý nghĩa trong mã nguồn. Java phân biệt chữ hoa và chữ thường, vì vậy `totalCount` và `TotalCount` là hai tên khác nhau.

## 2. Quy tắc đối với dấu gạch dưới đơn lẻ

Từ Java 9, dấu `_` được dành riêng làm từ khóa. Do đó, không thể sử dụng nó như một định danh thông thường.

Ví dụ các cách đặt tên sau không hợp lệ:

~~~java
int _ = 10;

class _ {
}

void _() {
}
~~~

Trình biên dịch từ chối các cách khai báo trên vì `_` không còn được phép làm tên định danh thông thường.

Quy tắc này áp dụng cho tên đứng riêng ở nhiều vị trí, không chỉ tên biến. Không thể đặt tên một lớp, phương thức, trường hoặc tham số thông thường bằng đúng một dấu gạch dưới.

### Các tên có chứa dấu gạch dưới vẫn hợp lệ

Việc dành riêng `_` không có nghĩa là Java cấm ký tự underscore trong mọi định danh. Tên có thêm ký tự khác vẫn có thể hợp lệ:

~~~java
int _count = 10;
int count_ = 20;
int user_name = 30;
int __ = 40;
~~~

Các tên trên không bằng đúng một ký tự `_`, nên không vi phạm quy tắc dành riêng từ Java 9. Khi viết mã ứng dụng, nên chọn tên mô tả ý nghĩa thay vì lạm dụng dấu gạch dưới hoặc đặt tên khó đọc.

## 3. Cách dùng dấu gạch dưới trong tên và số

Cần phân biệt underscore trong định danh với underscore trong một số dạng literal.

### Underscore trong định danh

Underscore có thể đứng đầu, đứng giữa hoặc đứng cuối một định danh nếu tên đó vẫn đáp ứng quy tắc định danh của Java và không phải chính ký tự `_`:

~~~java
String _firstName = "An";
String last_name = "Binh";
String account_id_ = "A102";
~~~

Đây là các định danh khác nhau và có thể được sử dụng như tên biến thông thường.

### Underscore trong literal số

Java cho phép dùng dấu gạch dưới để nhóm các chữ số trong literal số, giúp giá trị dài dễ đọc hơn:

~~~java
int oneMillion = 1_000_000;
long hexValue = 0xCAFE_BABE;
int binaryValue = 0b1010_0001;
~~~

Trong các ví dụ này, dấu gạch dưới chỉ là dấu phân tách chữ số trong literal số. Nó không phải tên định danh và không liên quan đến việc dùng `_` làm tên biến.

## 4. Unnamed variables và unnamed patterns từ Java 22

Từ Java 22, unnamed variables và unnamed patterns đã trở thành tính năng chính thức của Java. Chúng cho phép biểu thị rõ rằng một giá trị được khai báo hoặc được khớp nhưng không cần sử dụng trong phần còn lại của chương trình.

Đây là cách dùng có chủ đích của ký hiệu `_`, khác với việc đặt tên biến thông thường.

### Unnamed variable

Có thể khai báo một biến không tên trong những ngữ cảnh được Java hỗ trợ, chẳng hạn biến cục bộ hoặc biến của vòng lặp enhanced for:

~~~java
int processed = 0;

for (int _ : List.of(10, 20, 30)) {
    processed++;
}

System.out.println(processed);
~~~

Biến vòng lặp nhận từng phần tử, nhưng chương trình không cần đọc giá trị phần tử. Ký hiệu `_` thể hiện rõ ý định bỏ qua giá trị đó.

Unnamed variable không thể được tham chiếu như một biến có tên. Ví dụ, dù khai báo unnamed variable có thể hợp lệ từ Java 22, câu lệnh đọc giá trị bằng `_` vẫn không hợp lệ:

~~~java
int _ = 10;
System.out.println(_); // Không hợp lệ: unnamed variable không thể được tham chiếu
~~~

### Unnamed pattern

Unnamed pattern cho phép bỏ qua một thành phần khi kiểm tra hoặc phân rã giá trị bằng pattern matching. Ví dụ với record:

~~~java
record Point(int x, int y) {
}

Object value = new Point(7, 9);

if (value instanceof Point(int _, int y)) {
    System.out.println(y);
}
~~~

Pattern khớp với một đối tượng `Point`. Thành phần đầu tiên được kiểm tra là kiểu `int` nhưng không được gán vào một tên có thể sử dụng; thành phần thứ hai được liên kết với biến `y` để chương trình đọc giá trị.

Cách viết này giúp thể hiện chính xác thành phần nào cần dùng và thành phần nào được cố ý bỏ qua.

### Những ngữ cảnh thường gặp

| Ngữ cảnh | Ý nghĩa của `_` |
|---|---|
| Khai báo biến cục bộ | Nhận giá trị nhưng không tạo tên để tham chiếu |
| Enhanced for | Nhận phần tử vòng lặp khi không cần dùng giá trị |
| Lambda parameter | Bỏ qua tham số không cần thiết |
| Catch parameter | Nhận ngoại lệ nhưng không cần tham chiếu đối tượng ngoại lệ |
| Try-with-resources | Quản lý và tự đóng tài nguyên dù không cần dùng biến tài nguyên trong phần thân |
| Pattern matching | Bỏ qua thành phần hoặc giá trị được khớp |

Các cách dùng này yêu cầu source level hỗ trợ unnamed variables và unnamed patterns, tức Java 22 trở lên. Chúng vẫn tuân theo phạm vi cú pháp riêng của từng ngữ cảnh.

## 5. Ví dụ hoàn chỉnh với Java 22+

Tệp `UnderscoreIdentifierDemo.java`:

~~~java
import java.util.List;

public class UnderscoreIdentifierDemo {
    record Point(int x, int y) {
    }

    public static void main(String[] args) {
        int processed = 0;

        for (int _ : List.of(10, 20, 30)) {
            processed++;
        }

        Object value = new Point(7, 9);

        if (value instanceof Point(int _, int y)) {
            System.out.println("processed=" + processed);
            System.out.println("y=" + y);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 22 trở lên:

~~~bash
javac --release 22 UnderscoreIdentifierDemo.java
java UnderscoreIdentifierDemo
~~~

Kết quả chuẩn:

~~~text
processed=3
y=9
~~~

Ví dụ thể hiện hai trường hợp dùng underscore đúng mục đích: vòng lặp không cần giá trị từng phần tử và record pattern không cần thành phần đầu tiên. Chương trình vẫn có thể sử dụng thành phần thứ hai thông qua tên `y`.

## 6. Lỗi thường gặp và cách xử lý

| Cách viết hoặc tình huống | Kết quả | Cách xử lý |
|---|---|---|
| Dùng `_` làm tên biến thông thường | Không hợp lệ | Chọn tên có ý nghĩa như `count` hoặc `unusedValue` nếu thực sự cần tham chiếu |
| Dùng `_` làm tên lớp hoặc phương thức | Không hợp lệ | Đặt tên lớp hoặc phương thức theo quy tắc định danh |
| Khai báo unnamed variable rồi cố đọc `_` | Không hợp lệ | Nếu cần dùng giá trị, đặt tên biến thông thường |
| Dùng unnamed variables với source level trước Java 22 | Không được ngôn ngữ hỗ trợ | Chọn tên biến thông thường khi cần tương thích source level cũ |
| Nhầm `user_name` với tên chỉ gồm `_` | Hiểu sai quy tắc | Phân biệt định danh có nhiều ký tự với ký hiệu unnamed |

### Ví dụ phân biệt

~~~java
int _count = 1;  // Tên định danh hợp lệ
int count_ = 2;  // Tên định danh hợp lệ
int __ = 3;      // Tên định danh hợp lệ
int _ = 4;       // Unnamed variable từ Java 22, không phải tên thông thường

System.out.println(_count);
System.out.println(count_);
System.out.println(__);
// Không thể viết System.out.println(_);
~~~

## 7. Lưu ý khi review và nâng cấp mã nguồn

Khi review mã Java hiện hành, hãy kiểm tra cách sử dụng underscore theo đúng ngữ cảnh:

- Không dùng một dấu `_` làm tên định danh thông thường.
- Dùng tên biến rõ nghĩa nếu giá trị cần được đọc hoặc thay đổi.
- Chỉ dùng unnamed variable hoặc unnamed pattern ở các vị trí cú pháp được Java hỗ trợ.
- Kiểm tra source level và phiên bản JDK của dự án trước khi dùng cú pháp unnamed mới.
- Không tham chiếu unnamed variable trong biểu thức, vì nó không cung cấp một tên để truy cập giá trị.
- Không nhầm dấu phân tách chữ số trong literal với ký hiệu unnamed.

Khi chuyển mã sang Java 9 trở lên, các định danh cũ chỉ gồm một dấu gạch dưới cần được đổi tên để tuân thủ quy tắc từ khóa. Trong mã Java 22 trở lên, có thể dùng `_` trong các ngữ cảnh unnamed được hỗ trợ để biểu thị rõ giá trị không cần sử dụng.

## 8. Checklist ghi nhớ

- `_` đứng riêng không phải định danh thông thường trong Java 9 trở lên.
- Các tên như `_count`, `user_name`, `count_` và `__` vẫn có thể là định danh hợp lệ.
- Java 22 chuẩn hóa unnamed variables và unnamed patterns, dùng `_` để bỏ qua giá trị trong các ngữ cảnh được hỗ trợ.
- Unnamed variable không thể được đọc hoặc tham chiếu bằng ký hiệu `_`.
- Underscore trong literal số chỉ có vai trò phân tách chữ số.
- Luôn kiểm tra source level khi sử dụng tính năng ngôn ngữ mới.

Hiểu đúng sự khác biệt giữa định danh thông thường và unnamed syntax giúp tránh lỗi biên dịch, làm rõ ý định của mã nguồn và sử dụng các tính năng Java hiện hành một cách chính xác.