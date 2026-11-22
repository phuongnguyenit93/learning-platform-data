# Record thực thi interface bằng accessor hoặc phương thức bổ sung

## Mục tiêu

Trong Java, một record có thể triển khai interface giống như một class thông thường. Điểm hữu ích là accessor được Java tự sinh từ các record component có thể đáp ứng trực tiếp một phương thức của interface; khi chữ ký không khớp, record có thể khai báo thêm phương thức để thực hiện hợp đồng đó.

Sau bài này, bạn có thể xác định phương thức nào được accessor đáp ứng, khi nào cần tự viết phương thức, và cách kiểm tra hợp đồng interface khi biên dịch.

## 1. Record có thể triển khai interface

Record là một dạng class được thiết kế để biểu diễn dữ liệu. Ví dụ:

~~~java
record Person(String name, int age) {}
~~~

Java tự tạo các accessor công khai có tên theo component: `name()` trả về `String`, còn `age()` trả về `int`. Các accessor này không dùng tiền tố `get` như nhiều JavaBean truyền thống.

Record có thể khai báo một hoặc nhiều interface bằng từ khóa `implements`:

~~~java
interface HasName {
    String name();
}

record Person(String name, int age) implements HasName {}
~~~

Interface `HasName` yêu cầu một phương thức công khai `name()` không có tham số và trả về `String`. Accessor `name()` do record sinh ra có đúng chữ ký đó, nên nó tự đáp ứng hợp đồng interface. Không cần viết lại accessor trong record.

Record vẫn là một class `final` và trực tiếp kế thừa `java.lang.Record`; nó không thể kế thừa một class tùy ý khác. Tuy vậy, record có thể triển khai nhiều interface và cung cấp các phương thức cần thiết cho từng interface.

## 2. Khi accessor đáp ứng phương thức interface

Một accessor có thể đáp ứng phương thức trừu tượng của interface khi chữ ký tương thích. Hãy kiểm tra các điểm sau:

- Tên phương thức phải giống nhau.
- Danh sách tham số phải giống nhau. Accessor của component không nhận tham số.
- Kiểu trả về phải tương thích theo quy tắc override của Java. Với accessor tự sinh, kiểu trả về là kiểu của component; trường hợp thông thường nên khai báo interface với đúng kiểu đó.
- Phương thức triển khai phải có mức truy cập công khai. Accessor được sinh cho record là `public`, phù hợp với phương thức trừu tượng của interface.

Tên phương thức là một phần của hợp đồng. Nếu interface yêu cầu `getName()`, accessor `name()` không tự đáp ứng được chỉ vì cả hai cùng trả về tên. Khi đó, record phải cung cấp `getName()` một cách tường minh.

## 3. Khi cần khai báo phương thức bổ sung

Interface có thể yêu cầu một hành vi không tương ứng với accessor nào. Record có thể khai báo phương thức instance thông thường để đáp ứng yêu cầu ấy, miễn là tuân thủ chữ ký và mức truy cập của interface.

~~~java
interface HasDisplayName {
    String displayName();
}

record User(String firstName, String lastName) implements HasDisplayName {
    @Override
    public String displayName() {
        return firstName + " " + lastName;
    }
}
~~~

Ở ví dụ này, `firstName()` và `lastName()` là accessor được sinh tự động. Chúng không thể đáp ứng `displayName()` vì tên và mục đích của phương thức khác nhau. Record bổ sung `displayName()` để ghép hai component thành tên hiển thị. Chú thích `@Override` giúp trình biên dịch xác nhận phương thức đang ghi đè hoặc triển khai một phương thức có thật trong hợp đồng cha.

Nếu interface yêu cầu `getName()`, cách làm tương tự là khai báo `public String getName()` trong record và trả về component `name`. Java không tự đổi tên accessor từ `name()` thành `getName()`.

Các phương thức `default` trong interface đã có phần thân và có thể được record kế thừa mà không cần triển khai lại. Record chỉ cần ghi đè phương thức mặc định nếu muốn thay đổi hành vi. Phương thức `static` của interface được gọi qua interface và không phải là phương thức instance mà record cần triển khai.

## 4. Ví dụ hoàn chỉnh có thể chạy

Ví dụ dưới đây kết hợp cả hai cách: accessor `id()` do record sinh ra thực hiện hợp đồng `HasId`, còn phương thức bổ sung `description()` thực hiện hợp đồng `Describable`. Interface `Describable` cũng có một phương thức mặc định để minh họa cách dùng hành vi kế thừa.

Lưu toàn bộ nội dung mã vào tệp `Main.java`:

~~~java
interface HasId {
    String id();
}

interface Describable {
    String description();

    default boolean hasDescription() {
        return !description().isBlank();
    }
}

record Service(String id, String name, int port)
        implements HasId, Describable {

    @Override
    public String description() {
        return name + " listens on " + port;
    }
}

public class Main {
    public static void main(String[] args) {
        Service service = new Service("svc-1", "Catalog", 8080);

        HasId idView = service;
        Describable descriptionView = service;

        System.out.println(idView.id());
        System.out.println(descriptionView.description());
        System.out.println(descriptionView.hasDescription());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~text
javac Main.java
java Main
~~~

Kết quả chuẩn đầu ra chính xác:

~~~text
svc-1
Catalog listens on 8080
true
~~~

Giải thích kết quả:

1. `idView.id()` gọi accessor `id()` của record `Service`. Không cần khai báo lại phương thức này trong record.
2. `descriptionView.description()` gọi phương thức `description()` mà `Service` tự triển khai. Nội dung trả về được tạo từ hai giá trị `name` và `port`.
3. `descriptionView.hasDescription()` gọi phương thức `default` của `Describable`. Phương thức này gọi tiếp `description()` trên cùng đối tượng và kiểm tra kết quả có rỗng hay không.

Ví dụ cũng cho thấy tính đa hình: biến có kiểu interface có thể tham chiếu đến một đối tượng record. Qua biến đó, chương trình chỉ gọi được các phương thức có trong interface tương ứng, nhưng phần triển khai được thực thi trên đối tượng `Service`.

## 5. Các lỗi thường gặp

| Lỗi | Vì sao lỗi | Cách xử lý |
|---|---|---|
| Cho rằng `name()` đáp ứng `getName()` | Tên phương thức khác nhau | Khai báo thêm `getName()` nếu interface yêu cầu |
| Viết phương thức triển khai mà bỏ `public` | Phương thức interface cần mức truy cập công khai; không thể giảm mức truy cập khi triển khai | Khai báo `public` |
| Sai số lượng hoặc kiểu tham số | Phương thức không có chữ ký mà interface yêu cầu | Đối chiếu tên, tham số và kiểu trả về với interface |
| Kiểu trả về không tương thích | Phương thức không đáp ứng quy tắc override | Dùng kiểu trả về phù hợp với hợp đồng |
| Quên triển khai một phương thức trừu tượng | Record là class cụ thể, không thể để lại phương thức trừu tượng chưa được đáp ứng | Dùng accessor phù hợp hoặc khai báo phương thức còn thiếu |
| Cố khai báo một class cha tùy ý | Record đã trực tiếp kế thừa `java.lang.Record` | Dùng `implements` để kết hợp hành vi qua interface |

Lỗi chữ ký thường được phát hiện ngay khi biên dịch. Vì vậy, khi trình biên dịch báo record không triển khai một phương thức trừu tượng, hãy so sánh chính xác tên phương thức, danh sách tham số, kiểu trả về và mức truy cập trước khi thay đổi thiết kế.

## 6. Quy trình lựa chọn cách triển khai

1. Đọc interface và liệt kê các phương thức trừu tượng mà record phải cung cấp.
2. Với từng phương thức, kiểm tra xem có record component nào sinh ra accessor cùng chữ ký hay không.
3. Nếu accessor khớp, để Java tự sinh accessor và không viết lại không cần thiết.
4. Nếu không khớp, khai báo phương thức công khai trong record với chữ ký tương thích.
5. Kiểm tra những phương thức `default` có thể kế thừa và chỉ ghi đè khi có lý do.
6. Biên dịch chương trình, đọc lỗi nếu có, rồi chạy và đối chiếu đầu ra mong đợi.

## Ghi nhớ

Record triển khai interface theo hợp đồng phương thức của Java. Accessor tự sinh chỉ đáp ứng những phương thức có chữ ký phù hợp; nó không tự đáp ứng phương thức khác tên như `getName()`, phương thức có tham số, hay hành vi tính toán riêng. Khi interface yêu cầu hành vi bổ sung, hãy định nghĩa phương thức đó trong record với mức truy cập và chữ ký chính xác.