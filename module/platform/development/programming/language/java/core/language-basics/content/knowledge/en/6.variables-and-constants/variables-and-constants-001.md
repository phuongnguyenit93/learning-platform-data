# Khai báo biến, khởi tạo và phép gán trong Java

## 1. Ba thao tác khác nhau

**Biến (variable)** là một vị trí lưu trữ có tên và có kiểu. Trong Java 17+, kiểu của biến được kiểm tra lúc biên dịch. Học cách sử dụng biến bắt đầu từ ba thao tác:

~~~java
int quantity;       // (1) Khai báo: tên quantity có kiểu int
quantity = 3;       // (2) Gán giá trị đầu tiên cho biến
quantity = 4;       // (3) Gán lại: thay giá trị đang lưu
~~~

Bạn cũng có thể **khai báo và khởi tạo trong cùng một câu lệnh**:

~~~java
int quantity = 3;
~~~

| Thao tác | Ví dụ | Điều xảy ra |
|---|---|---|
| Khai báo (*declaration*) | `int count;` | Giới thiệu biến `count` với kiểu `int` |
| Khởi tạo cùng khai báo (*initialization*) | `int count = 3;` | Tạo biến và cấp ngay giá trị đầu |
| Gán sau khai báo (*assignment*) | `count = 3;` | Đưa giá trị vào biến đã khai báo |
| Gán lại (*reassignment*) | `count = 4;` | Thay giá trị cũ bằng giá trị mới |
| Đọc biến | `System.out.println(count);` | Sử dụng giá trị biến đang giữ |

**Điểm cốt lõi:** dấu `=` ở đây là **phép gán**, không phải dấu “bằng nhau” của toán học. `count = 4` yêu cầu Java lưu giá trị mới; còn `count == 4` là biểu thức **so sánh** trả về `boolean`.

## 2. Cú pháp khai báo và quy tắc kiểu

Khai báo biến cục bộ thông thường có dạng:

~~~java
Type variableName;
Type otherName = expression;
~~~

Ví dụ:

~~~java
int age = 20;
long population = 8_000_000_000L;
double temperature = 26.5;
boolean active = true;
char grade = 'A';
String city = "Ha Noi";
~~~

Ở đây `int`, `long`, `double`, `boolean`, `char` là các kiểu primitive; `String` là kiểu tham chiếu. Biểu thức ở vế phải phải có kiểu **có thể gán** cho biến theo quy tắc chuyển kiểu của Java.

Một khai báo cũng có thể khai báo nhiều biến cùng kiểu:

~~~java
int width = 3, height = 4;
int area = width * height;
~~~

Tuy hợp lệ, trong mã nghiệp vụ nên tách khai báo nếu nhiều biến có ý nghĩa khác nhau hoặc initializer phức tạp. Không thể dùng chung một khai báo để trộn kiểu tùy ý như `int a = 1, b = "hai";`.

### Tên và phạm vi biến

~~~java
int subtotal = 100;
if (subtotal > 0) {
    int discount = 10;
    System.out.println(subtotal - discount); // 90
}
// System.out.println(discount); // Lỗi: discount ngoài phạm vi
~~~

Biến cục bộ thường có phạm vi trong block chứa khai báo, tính từ nơi khai báo theo quy tắc của Java. **Khai báo một lần** rồi gán lại khi cần; không khai báo lại một biến cục bộ cùng tên ở vị trí bị cấm:

~~~java
int count = 1;
count = 2;       // Đúng: gán lại
// int count = 3; // Lỗi: trùng khai báo trong cùng block
~~~


## 3. Điều kiện để một phép đọc hợp lệ

Với **biến cục bộ**, khai báo xong chưa đủ để đọc: Java yêu cầu nó đã được gán chắc chắn trước lần đọc ấy (*definite assignment*).

~~~java
int score;
// System.out.println(score); // Lỗi: có thể chưa được gán
score = 80;
System.out.println(score); // 80
~~~

**Tham số** nhận giá trị từ lời gọi; **field và phần tử mảng** có giá trị mặc định theo kiểu. Những cơ chế này khác nhau, nên đừng suy rằng `int score;` trong phương thức tự nhận 0. Phần phân tích đường đi `if`, vòng lặp và `final` thuộc bài chuyên sâu về *definite assignment*.

## 4. Gán giá trị và đánh giá vế phải

Trong một phép gán đơn giản:

~~~java
int unitPrice = 120;
int quantity = 3;
int subtotal = unitPrice * quantity;
~~~

Java đánh giá biểu thức `unitPrice * quantity` rồi gán kết quả `360` vào `subtotal`.

Nếu sau đó:

~~~java
quantity = 4;
System.out.println(subtotal); // 360
subtotal = unitPrice * quantity;
System.out.println(subtotal); // 480
~~~

Thì `subtotal` **không tự cập nhật** khi `quantity` đổi. Biến Java giữ giá trị đã được tính ở thời điểm gán; nó không phải ô công thức của bảng tính.

Phép gán cũng là một **biểu thức có kết quả**, nên có thể dùng gán nối tiếp:

~~~java
int first, second;
first = second = 9; // Tương đương first = (second = 9)
System.out.println(first + ", " + second); // 9, 9
~~~

Phép gán có tính kết hợp từ phải sang trái. Tuy nhiên, đừng lạm dụng các phép gán lồng nhau làm cho code khó theo dõi; câu lệnh riêng thường dễ kiểm thử hơn.

### `=` khác `==`

~~~java
int points = 10;
points = 20;                      // Gán lại
boolean matches = points == 20;  // So sánh, true
~~~

Trong một điều kiện boolean, viết nhầm phép gán có thể **vẫn biên dịch và gây bug**:

~~~java
boolean approved = false;
if (approved = true) { // Hợp lệ, nhưng đang thay đổi approved!
    System.out.println("APPROVED");
}
~~~

Nếu mục tiêu là kiểm tra, viết `if (approved)`. Với số nguyên, `if (points = 20)` không biên dịch vì biểu thức gán kiểu `int`, không phải `boolean`.


## 5. Giới hạn cần biết trước khi gán

Một phép gán hợp lệ phải **tương thích với kiểu khai báo**; ví dụ `int amount = 10; long total = amount;` hợp lệ, còn `int amount = "10";` là lỗi kiểu. Với `var`, compiler suy ra kiểu **tĩnh** từ initializer; với `final`, việc gán lại biến bị giới hạn. Các chi tiết về miền kiểu, chuyển hẹp, `final` và tính thay đổi của object có bài riêng trong chương.

Ở đây hãy luôn hỏi: biến nào đang được gán, biểu thức nào phải được đánh giá trước, và giá trị đã gán có cần tính lại khi đầu vào thay đổi không?

## 6. Ví dụ Java 17: lần theo từng phép gán

Lưu tệp `AssignmentWalkthrough.java`:

~~~java
public final class AssignmentWalkthrough {
    public static void main(String[] args) {
        int quantity;                 // Khai báo
        quantity = 3;                 // Gán lần đầu
        int unitPrice = 120;          // Khai báo và khởi tạo
        int total = unitPrice * quantity;
        System.out.println("start=" + total);

        quantity = 4;                 // Gán lại một đầu vào
        System.out.println("stored=" + total);
        total = unitPrice * quantity; // Tính lại có chủ đích
        System.out.println("recomputed=" + total);

        int left, right;
        left = right = 9;             // Gán nối tiếp từ phải qua trái
        System.out.println("chain=" + left + "," + right);
        boolean same = total == 480;  // So sánh, không gán
        System.out.println("same=" + same);

        int earlier = quantity;       // Sao chép giá trị int
        quantity = 5;
        System.out.println("copy=" + earlier + ", now=" + quantity);
    }
}
~~~

Dùng JDK 17 trở lên trong thư mục chứa tệp:

~~~bash
javac --release 17 -encoding UTF-8 AssignmentWalkthrough.java
java -cp . AssignmentWalkthrough
~~~

Kết quả:

~~~text
start=360
stored=360
recomputed=480
chain=9,9
same=true
copy=4, now=5
~~~

`stored=360` không tự chuyển thành 480 sau khi `quantity` đổi, vì biến `total` đã nhận giá trị của lần tính trước. `recomputed=480` chỉ xuất hiện sau một **phép gán mới**. `chain=9,9` là kết quả của `left = (right = 9)`; `same=true` đến từ phép so sánh `==`. Cuối cùng, `earlier` vẫn bằng 4 vì phép gán từ biến `int` sao chép giá trị, không tạo liên kết tự cập nhật.

## 7. Những nhầm lẫn thường gặp

| Cách viết | Vấn đề | Cách nhìn đúng |
|---|---|---|
| `int n; System.out.println(n);` trong method | Biến cục bộ chưa được gán | Gán chắc chắn trước khi đọc |
| `int n = 1; int n = 2;` trong cùng block | Khai báo trùng | Viết `n = 2;` nếu muốn gán lại |
| `int a, b = 5;` | Chỉ `b` được khởi tạo | Mỗi tên có initializer riêng |
| `if (approved = true)` | Thay đổi `approved` trong lúc kiểm tra | Viết `if (approved)` nếu chỉ kiểm tra |
| Đổi `quantity` rồi tưởng `total` đổi theo | Phép gán không tạo công thức sống | Tính và gán lại `total` khi cần |

Khi debug, hãy đánh dấu **điểm đọc** và **điểm ghi** của từng biến. Kiểm tra từng RHS theo thứ tự thực thi; đừng đọc một dòng gán như phương trình toán học.

## 8. Luyện tập kèm giải thích

**Bài 1.** Viết riêng hai phiên bản: `int score; score = 90;` và `int score = 90;`. Cả hai in ra bao nhiêu?  
*Đáp án:* Cùng in `90`; khác nhau ở thời điểm thực hiện khai báo/khởi tạo.

**Bài 2.** Dự đoán:

~~~java
int price = 25;
int count = 2;
int total = price * count;
count = 3;
System.out.println(total + "," + (price * count));
~~~

*Đáp án:* `50,75`; `total` giữ kết quả đã gán, biểu thức mới dùng `count = 3`.

**Bài 3.** `int first, second; first = second = 7;` khác gì `first == second`?  
*Đáp án:* Câu đầu gán cả hai biến; biểu thức thứ hai so sánh giá trị và trả về `boolean`.

**Bài 4.** Với `int a = 2; int b = a; a = 9;`, `b` có tự đổi không?  
*Đáp án:* Không, `b` vẫn bằng 2 vì là bản sao của giá trị tại thời điểm gán.

### Tự kiểm tra

- [ ] Phân biệt khai báo, khởi tạo, gán đầu, gán lại và đọc biến.
- [ ] Dự đoán đúng thứ tự đánh giá RHS và tác dụng của phép gán.
- [ ] Biết `=` gán giá trị còn `==` so sánh.
- [ ] Không nhầm biến Java với công thức tự cập nhật.
- [ ] Biết ranh giới cơ bản về kiểu, phạm vi và gán trước khi đọc.
- [ ] Chạy `AssignmentWalkthrough.java` và giải thích từng dòng kết quả.

**Kết luận:** Phép gán thay **giá trị được giữ trong biến tại một thời điểm**. Muốn thay kết quả tính toán, chương trình phải thực hiện phép gán khác. Học được điều này trước sẽ giúp bạn hiểu sâu hơn về kiểu, phạm vi, `final` và giá trị mặc định ở các bài kế tiếp.
