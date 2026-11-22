# Sử dụng record pattern trong biểu thức instanceof

Trong Java 21, **record pattern** cho phép kiểm tra một giá trị có thuộc kiểu record mong muốn hay không và lấy các thành phần của record ngay trong biểu thức `instanceof`. Cách viết này giúp điều kiện kiểm tra kiểu và thao tác phân rã dữ liệu nằm cùng một chỗ, giảm việc tạo biến trung gian rồi gọi từng accessor.

Record patterns là tính năng chính thức của Java 21, vì vậy có thể dùng với cấu hình biên dịch Java 21 thông thường, không cần bật preview. Nội dung dưới đây tập trung vào `instanceof`, từ record đơn giản đến record lồng nhau và cách xử lý giá trị `null`.

## 1. Record pattern giải quyết việc gì?

Giả sử ứng dụng có record biểu diễn tọa độ:

```java
record Point(int x, int y) {}
```

Với cách kiểm tra kiểu thông thường, chương trình cần kiểm tra đối tượng, giữ tham chiếu record rồi đọc từng component:

```java
if (value instanceof Point point) {
    int x = point.x();
    int y = point.y();
    System.out.println("x=" + x + ", y=" + y);
}
```

Record pattern cho phép viết trực tiếp cấu trúc cần khớp:

```java
if (value instanceof Point(int x, int y)) {
    System.out.println("x=" + x + ", y=" + y);
}
```

Trong ví dụ này, `Point(int x, int y)` vừa kiểm tra giá trị có phải là một `Point` phù hợp hay không, vừa tạo hai pattern variable `x` và `y` chứa giá trị component tương ứng. Nếu pattern khớp, các biến này được dùng trong thân `if`.

## 2. Cú pháp và cách hoạt động

Cấu trúc tổng quát:

```java
expression instanceof RecordType(componentPattern1, componentPattern2, ...)
```

Trong đó:

- `expression` là giá trị cần kiểm tra, thường có kiểu tham chiếu rộng như `Object` hoặc một interface.
- `RecordType` phải là kiểu record.
- Các component pattern xuất hiện theo đúng thứ tự khai báo component trong phần header của record.
- Số component pattern phải bằng số component của record.
- Mỗi component pattern có thể là một type pattern, `var` pattern hoặc một record pattern lồng nhau.

Ví dụ:

```java
record User(String username, int age) {}

static void inspect(Object value) {
    if (value instanceof User(String username, int age)) {
        System.out.println(username + " is " + age + " years old");
    }
}
```

`User` khai báo hai component theo thứ tự `username`, `age`, vì vậy pattern cũng phải liệt kê theo thứ tự đó. Pattern không dựa vào tên component để tự tìm vị trí; vị trí trong danh sách mới quyết định component nào được phân rã.

Khi kiểm tra, Java xác định giá trị có phù hợp với kiểu record hay không, sau đó lấy giá trị các component thông qua accessor tương ứng và kiểm tra từng component pattern. Nếu một component pattern không khớp, toàn bộ record pattern không khớp. Các accessor của record được gọi trong quá trình phân rã; nếu record định nghĩa accessor tùy chỉnh, logic của accessor đó cũng được thực thi.

Record pattern chỉ phân rã giá trị hiện có. Nó không tạo record mới, không gọi constructor và không so sánh các component với một bộ giá trị cố định.

## 3. Sử dụng `instanceof` với record đơn giản

Tạo file `RecordPatternDemo.java`:

```java
record Point(int x, int y) {}

public class RecordPatternDemo {
    static String describe(Object value) {
        if (value instanceof Point(int x, int y)) {
            return "Point(" + x + ", " + y + ")";
        }

        return "Giá trị không phải Point";
    }

    public static void main(String[] args) {
        Object first = new Point(3, 4);
        Object second = "Java 21";

        System.out.println(describe(first));
        System.out.println(describe(second));
    }
}
```

Biên dịch và chạy bằng JDK 21:

```shell
javac --release 21 RecordPatternDemo.java
java RecordPatternDemo
```

Kết quả:

```text
Point(3, 4)
Giá trị không phải Point
```

Ở lần gọi đầu, giá trị là một `Point`, vì vậy pattern khớp và chương trình lấy được `x = 3`, `y = 4`. Ở lần gọi thứ hai, giá trị là chuỗi nên biểu thức `instanceof` trả về `false` và chương trình đi đến nhánh còn lại.

Nếu muốn để trình biên dịch suy luận kiểu của component từ khai báo record, có thể dùng `var`:

```java
if (value instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

Với `Point`, kiểu suy luận của `x` và `y` là `int`. Dùng kiểu tường minh như `int x` khi muốn thể hiện rõ kiểu dữ liệu tại điểm sử dụng; dùng `var` khi kiểu component đã rõ từ record và muốn giữ pattern ngắn gọn.

## 4. Phạm vi sử dụng của pattern variable

Các biến được khai báo trong record pattern tuân theo quy tắc flow scoping của pattern matching. Chúng chỉ có thể được sử dụng tại vị trí mà trình biên dịch xác định pattern đã khớp.

Ví dụ, có thể dùng component ngay trong phần điều kiện tiếp theo của toán tử `&&`:

```java
if (value instanceof Point(int x, int y) && x >= 0 && y >= 0) {
    System.out.println("Point nằm trong góc phần tư thứ nhất hoặc trên trục");
}
```

Các biểu thức kiểm tra `x` và `y` chỉ được đánh giá sau khi record pattern khớp, nên hai biến đã có giá trị hợp lệ tại vị trí đó.

Cũng có thể dùng điều kiện phủ định để kết thúc sớm:

```java
static int manhattanDistance(Object value) {
    if (!(value instanceof Point(int x, int y))) {
        throw new IllegalArgumentException("Expected Point");
    }

    // Sau nhánh throw, chương trình chỉ tiếp tục khi pattern đã khớp.
    return Math.abs(x) + Math.abs(y);
}
```

Sau câu lệnh `if`, trình biên dịch biết rằng mọi đường đi còn tiếp tục đều đã vượt qua điều kiện `instanceof`; vì vậy `x` và `y` có thể được sử dụng ở phần còn lại của phương thức.

Không thể sử dụng pattern variable ở một vị trí mà pattern có thể chưa khớp. Chẳng hạn, không đặt việc dùng `x` ở một nhánh điều kiện có thể chạy khi biểu thức `instanceof` trả về `false`.

## 5. Phân rã record lồng nhau

Record pattern có thể lồng một record pattern khác để đi sâu vào cấu trúc dữ liệu. Điều này hữu ích khi một record chứa một record khác.

```java
record Address(String city, String country) {}
record Person(String name, Address address) {}

static String describePerson(Object value) {
    if (value instanceof Person(
            String name,
            Address(var city, var country))) {
        return name + " sống tại " + city + ", " + country;
    }

    return "Không phải Person có Address phù hợp";
}
```

Pattern ngoài kiểm tra `Person` và lấy hai component. Pattern lồng `Address(var city, var country)` tiếp tục kiểm tra component `address` có phải một `Address` phù hợp hay không, rồi lấy `city` và `country`.

Các component pattern được kiểm tra từ trái sang phải. Nếu `value` không phải `Person`, hoặc component `address` không khớp với record pattern `Address(...)`, toàn bộ biểu thức `instanceof` trả về `false` và thân `if` không chạy.

Có thể lồng nhiều cấp nếu cấu trúc dữ liệu yêu cầu, nhưng nên giữ pattern đủ dễ đọc. Với cấu trúc quá sâu hoặc nhiều component tùy chọn, tách thành các bước kiểm tra thường giúp xử lý lỗi và giá trị thiếu rõ ràng hơn.

## 6. Xử lý `null` trong record pattern

`instanceof` không khớp với giá trị `null`. Vì vậy, nếu biến được kiểm tra là `null`, record pattern trả về `false` và không có pattern variable nào được đưa vào phạm vi sử dụng.

```java
Object value = null;

if (value instanceof Point(int x, int y)) {
    // Không chạy khi value là null.
}
```

Với component tham chiếu, cần phân biệt type pattern và `var` pattern:

- Type pattern như `String name` chỉ khớp khi component có giá trị phù hợp với kiểu `String`; component `null` không khớp.
- `var` pattern nhận giá trị component mà không yêu cầu kiểm tra kiểu bổ sung, kể cả khi giá trị là `null`.
- Record pattern lồng nhau không khớp nếu component cần phân rã là `null`.

Giả sử địa chỉ của một người có thể chưa được cung cấp. Có thể lấy component bằng `var`, sau đó kiểm tra null riêng:

```java
record Address(String city, String country) {}
record Person(String name, Address address) {}

static String describePerson(Object value) {
    if (value instanceof Person(var name, var address)) {
        if (address == null) {
            return name + " chưa cung cấp địa chỉ";
        }

        return name + " sống tại " + address.city();
    }

    return "Không phải Person";
}
```

Ở đây, `var address` có kiểu được suy luận là `Address` và vẫn nhận được giá trị `null`. Sau khi kiểm tra null, chương trình có thể gọi accessor an toàn. Nếu dùng trực tiếp `Address(var city, var country)` trong pattern lồng, trường hợp `address == null` sẽ làm toàn bộ pattern không khớp.

Với component có thể null, hãy chọn cách viết thể hiện rõ ý định: phân rã lồng khi component bắt buộc tồn tại; dùng `var` rồi kiểm tra riêng khi component là tùy chọn.

## 7. So sánh type pattern và record pattern

Hai cách viết đều hợp lệ trong Java 21 nhưng phục vụ nhu cầu khác nhau:

| Cách viết | Kết quả khi khớp | Nên dùng khi |
|---|---|---|
| `value instanceof Point point` | Có biến `point` tham chiếu đến toàn bộ record | Cần truyền record sang phương thức khác hoặc dùng nhiều accessor ở các vị trí khác nhau |
| `value instanceof Point(int x, int y)` | Có trực tiếp các biến component `x` và `y` | Chỉ cần một số component tại nhánh xử lý hiện tại |
| `value instanceof Person(var name, Address(var city, var country))` | Phân rã cả record ngoài và record lồng | Cần xử lý dữ liệu nằm trong cấu trúc record lồng nhau |

Record pattern không làm cho type pattern cũ mất tác dụng. Hãy chọn cách viết theo dữ liệu cần dùng. Nếu cần giữ toàn bộ đối tượng, bind một biến record; nếu cần các component để xử lý ngay, record pattern làm rõ cấu trúc cần khớp.

## 8. Lỗi thường gặp và cách khắc phục

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không biên dịch được khi dùng record pattern | Đang dùng compiler thấp hơn Java 21 hoặc cấu hình release thấp hơn 21 | Kiểm tra `javac --version` và cấu hình mức phát hành là 21 |
| Số component pattern không khớp | Pattern liệt kê thiếu hoặc thừa component so với record header | Đối chiếu thứ tự và số component trong khai báo record |
| Dùng sai kiểu component | Type pattern không phù hợp với kiểu component được khai báo | Dùng kiểu chính xác hoặc `var` để trình biên dịch suy luận |
| Thân `if` không chạy dù đối tượng là record | Một component pattern không khớp, hoặc giá trị cần kiểm tra là `null` | Kiểm tra kiểu và giá trị của từng component; chú ý record pattern lồng nhau |
| Pattern variable không được nhận diện | Biến được dùng ngoài phạm vi flow scoping | Chỉ sử dụng biến ở nhánh mà trình biên dịch xác định pattern đã khớp |
| Record lồng không khớp khi component bị thiếu | Component dùng nested record pattern nhưng giá trị thực tế là `null` | Lấy component bằng `var`, kiểm tra null rồi mới phân rã tiếp |

Một lỗi khác là dùng record pattern cho một class thông thường có các getter giống record. Record pattern yêu cầu kiểu được kiểm tra phải là record; một class thông thường không trở thành record chỉ vì có các phương thức accessor tương tự.

Trong mã Java 21 không bật preview, không dùng `_` làm unnamed pattern để bỏ qua component. Nếu cần nhận một component mà không sử dụng giá trị, đặt một tên biến phù hợp, chẳng hạn `var ignoredValue`. Unnamed patterns và variables chưa phải tính năng chính thức của Java 21.

## 9. Checklist khi sử dụng record pattern với `instanceof`

- Kiểu được dùng trong record pattern thực sự là một record.
- Số lượng và thứ tự component pattern khớp với khai báo record.
- Kiểu pattern của từng component tương thích với kiểu component tương ứng.
- Chỉ sử dụng pattern variable trong phạm vi mà pattern chắc chắn đã khớp.
- Đã xác định cách xử lý khi giá trị đầu vào hoặc component tham chiếu là `null`.
- Với record lồng nhau, chỉ phân rã trực tiếp khi component lồng được kỳ vọng có giá trị.
- Các accessor của record không chứa tác dụng phụ bất ngờ vì chúng được gọi trong quá trình phân rã.
- Project biên dịch theo Java 21; record patterns không cần tùy chọn preview.

Record pattern trong `instanceof` giúp chương trình kiểm tra kiểu và lấy dữ liệu record trong cùng một biểu thức. Khi kết hợp type pattern, `var` pattern và nested record pattern đúng chỗ, mã Java 21 có thể thể hiện rõ cấu trúc dữ liệu, đồng thời giữ cho việc kiểm tra null và phạm vi biến dễ theo dõi.
