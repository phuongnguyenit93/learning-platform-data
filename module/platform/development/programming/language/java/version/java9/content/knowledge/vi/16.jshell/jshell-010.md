# Tách thử nghiệm ngắn khỏi mã ứng dụng cần kiểm thử đầy đủ

JShell là môi trường tương tác của JDK, cho phép nhập và chạy từng biểu thức, câu lệnh hoặc khai báo Java ngay trong một phiên làm việc. Nó rất hữu ích khi cần kiểm tra nhanh một giả thuyết về API, kiểu dữ liệu, phép tính hoặc cách xử lý một giá trị. Tuy nhiên, một đoạn mã chạy đúng trong JShell chỉ chứng minh đoạn thử nghiệm đó hoạt động trong ngữ cảnh hiện tại. Nó chưa chứng minh ứng dụng hoàn chỉnh biên dịch đúng, phối hợp đúng với các thành phần khác hoặc đáp ứng yêu cầu khi chạy trong môi trường thật.

Cách làm hiệu quả là dùng JShell để khám phá nhanh, sau đó chuyển những hành vi quan trọng thành kiểm thử tự động trong dự án. Hai bước phục vụ hai mục tiêu khác nhau và bổ trợ cho nhau.

## 1. Việc nào phù hợp với JShell?

JShell phù hợp với những câu hỏi nhỏ, có thể kiểm tra trong một phiên độc lập:

- Một biểu thức Java trả về giá trị nào với dữ liệu cụ thể?
- Một API có phương thức hoặc overload nào phù hợp?
- Một phép chuyển kiểu, xử lý chuỗi, collection hoặc Stream có tạo ra kết quả mong đợi không?
- Một trường hợp biên như chuỗi rỗng, giá trị bằng 0 hoặc đầu vào âm được xử lý thế nào?
- Một lớp đã biên dịch có thể được gọi ra sao từ mã đang viết?
- Một ý tưởng thuật toán có đúng trước khi đưa vào mã nguồn chính không?

Ví dụ, có thể kiểm tra nhanh quy tắc tính giá sau giảm giá. Đoạn mã dưới đây dùng số nguyên để biểu diễn đơn vị tiền nhỏ nhất; phép chia nguyên làm tròn xuống:

~~~java
int discountedPrice(int price, int percent) {
    if (price < 0) {
        throw new IllegalArgumentException("price must be non-negative");
    }
    if (percent < 0 || percent > 100) {
        throw new IllegalArgumentException("percent must be between 0 and 100");
    }
    return Math.toIntExact((long) price * (100 - percent) / 100);
}

System.out.println(discountedPrice(360, 10));
System.out.println(discountedPrice(0, 10));
System.out.println(discountedPrice(1, 100));

assert discountedPrice(360, 10) == 324;
assert discountedPrice(0, 10) == 0;
assert discountedPrice(1, 100) == 0;
System.out.println("quick checks passed");
~~~

Kết quả:

~~~text
324
0
0
quick checks passed
~~~

JShell có thể chạy cả khai báo phương thức và câu lệnh assert. Đây là cách tốt để thử nhanh một vài giá trị đại diện và xác nhận một giả thuyết trước khi viết kiểm thử chính thức.

Ví dụ trên chưa phải đặc tả đầy đủ cho nghiệp vụ tiền tệ. Quy tắc làm tròn, đơn vị tiền, thuế, giới hạn giá trị và cách xử lý số thập phân phải được xác định theo yêu cầu thực tế. JShell giúp thử quy tắc; nhóm phát triển vẫn phải quyết định và ghi lại quy tắc đúng của ứng dụng.

## 2. Chạy thử tương tác và giữ lại thí nghiệm

Khởi động JShell bằng lệnh:

~~~shell
jshell
~~~

Sau đó nhập các khai báo và biểu thức trực tiếp. JShell giữ trạng thái trong phiên: biến, phương thức và lớp đã khai báo có thể được sử dụng ở các snippet tiếp theo. Điều này thuận tiện khi khám phá, nhưng cũng có thể làm kết quả phụ thuộc vào thứ tự những gì đã nhập.

Các lệnh hữu ích trong phiên hiện tại:

| Lệnh | Công dụng |
|---|---|
| /vars | Xem các biến đang hoạt động và giá trị của chúng. |
| /methods | Xem các phương thức đã khai báo. |
| /types | Xem các kiểu như lớp và interface. |
| /imports | Xem các import đang có hiệu lực. |
| /list | Xem mã nguồn snippet đã nhập cùng ID. |
| /history | Xem lịch sử lệnh và mã đã nhập. |
| /save -all explore.jsh | Lưu mã snippet vào tệp để dùng lại. |
| /open explore.jsh | Nạp và chạy nội dung tệp trong phiên hiện tại. |
| /reset | Tạo lại ngữ cảnh JShell và xóa các khai báo của phiên. |
| /exit | Thoát JShell. |

Một thí nghiệm cần dùng lại nên được lưu thành tệp .jsh thay vì chỉ tồn tại trong lịch sử terminal. Có thể chạy lại tệp bằng:

~~~shell
jshell --feedback concise explore.jsh
~~~

Khi một kết quả bất ngờ xuất hiện, hãy mở một phiên mới hoặc dùng /reset rồi chạy lại thí nghiệm từ đầu. Việc này giúp phát hiện trường hợp mã đang dựa vào một biến hoặc khai báo cũ còn sót trong phiên.

## 3. Thử trực tiếp lớp đã biên dịch của ứng dụng

JShell không chỉ dùng cho biểu thức độc lập. Có thể nạp lớp ứng dụng đã biên dịch vào classpath để kiểm tra cách gọi API thực tế.

Với dự án Maven, sau khi biên dịch mã chính:

~~~shell
mvn compile
jshell --class-path target/classes
~~~

Với dự án Gradle:

~~~shell
./gradlew classes
jshell --class-path build/classes/java/main
~~~

Trong JShell, import lớp thuộc package của ứng dụng rồi gọi thử:

~~~java
import com.example.pricing.DiscountCalculator;

DiscountCalculator calculator = new DiscountCalculator();
System.out.println(calculator.discountedPrice(360, 10));
~~~

Thay tên package và lớp bằng cấu trúc thật của dự án. Nếu lớp phụ thuộc vào thư viện bên ngoài, classpath của JShell cũng phải chứa các thư viện cần thiết. Việc nạp được một lớp đã biên dịch giúp khám phá API thuận tiện, nhưng không thay thế bước build và kiểm thử của dự án.

## 4. Vì sao JShell không thay thế kiểm thử ứng dụng?

Một phiên JShell thường là chuỗi thao tác tương tác. Người chạy có thể vô tình dựa vào biến, import hoặc trạng thái được tạo từ trước. Một phiên mới, một máy khác hoặc một lần chạy tự động có thể không có cùng trạng thái đó.

Ngoài ra, đoạn mã snippet không tự kiểm tra toàn bộ cấu trúc của ứng dụng. JShell không tự chạy đầy đủ quy trình build, test, đóng gói, nạp tài nguyên, khởi tạo dependency injection, migration cơ sở dữ liệu hoặc cấu hình môi trường của dự án. Ngay cả khi nạp được lớp đã biên dịch, điều đó cũng không xác nhận các module khác đang phối hợp đúng.

Các trường hợp sau cần kiểm thử trong dự án:

- Hành vi của nhiều lớp khi phối hợp và trao đổi dữ liệu.
- Đọc ghi cơ sở dữ liệu, transaction, migration và rollback.
- Gọi HTTP, xử lý timeout, retry, lỗi mạng và xác thực.
- Đọc cấu hình, biến môi trường, tệp tài nguyên và quyền truy cập.
- Đồng thời, đồng bộ, race condition và xử lý vòng đời tài nguyên.
- Serialization, tương thích dữ liệu và giao tiếp giữa các module.
- Các quy tắc nghiệp vụ có nhiều nhánh, nhiều trường hợp biên hoặc ảnh hưởng tới dữ liệu thật.

Một lần chạy thành công trong JShell cũng không đảm bảo mã nguồn của dự án biên dịch sạch từ đầu. Muốn xác nhận điều đó, phải chạy build và test bằng công cụ mà dự án sử dụng.

## 5. Chuyển thí nghiệm thành unit test có thể chạy lặp lại

Sau khi tìm được hành vi mong muốn trong JShell, hãy đưa quy tắc ổn định vào lớp ứng dụng và viết unit test. Ví dụ lớp tính giá sau giảm giá:

~~~java
package com.example.pricing;

public final class DiscountCalculator {
    public int discountedPrice(int price, int percent) {
        if (price < 0) {
            throw new IllegalArgumentException("price must be non-negative");
        }
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException("percent must be between 0 and 100");
        }
        return Math.toIntExact((long) price * (100 - percent) / 100);
    }
}
~~~

Trong dự án đã cấu hình JUnit Jupiter, có thể viết kiểm thử tương ứng:

~~~java
package com.example.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class DiscountCalculatorTest {
    private final DiscountCalculator calculator = new DiscountCalculator();

    @Test
    void appliesPercentageDiscount() {
        assertEquals(324, calculator.discountedPrice(360, 10));
    }

    @Test
    void handlesZeroPriceAndFullDiscount() {
        assertEquals(0, calculator.discountedPrice(0, 10));
        assertEquals(0, calculator.discountedPrice(1, 100));
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(
            IllegalArgumentException.class,
            () -> calculator.discountedPrice(-1, 10)
        );
    }

    @Test
    void rejectsPercentageOutsideRange() {
        assertThrows(
            IllegalArgumentException.class,
            () -> calculator.discountedPrice(100, -1)
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> calculator.discountedPrice(100, 101)
        );
    }
}
~~~

Mỗi test có tên mô tả hành vi, thiết lập dữ liệu rõ ràng và kiểm tra kết quả bằng assertion. Khi test thất bại, runner chỉ ra test nào không đạt để có thể điều tra và sửa lỗi. Bộ test có thể được chạy lại trên máy lập trình viên và trong CI mà không cần nhập từng lệnh bằng tay.

Chạy test theo build tool của dự án:

~~~shell
# Maven
./mvnw test

# Gradle
./gradlew test
~~~

Trên Windows có thể dùng các tệp wrapper tương ứng là mvnw.cmd và gradlew.bat. Dự án phải có dependency và cấu hình test runner phù hợp với JUnit Jupiter; hãy giữ phiên bản thư viện theo quản lý dependency hiện tại của dự án.

## 6. Phân biệt unit test, integration test và end-to-end test

Không phải mọi kiểm thử đều cần chạy qua toàn bộ ứng dụng. Chọn phạm vi nhỏ nhất vẫn xác nhận được hành vi cần thiết:

| Loại kiểm thử | Phạm vi | Ví dụ |
|---|---|---|
| Unit test | Một lớp hoặc một đơn vị logic, với phụ thuộc được kiểm soát. | Tính giá, kiểm tra dữ liệu đầu vào, chuyển đổi giá trị. |
| Integration test | Nhiều thành phần thật được kết nối với nhau. | Repository với cơ sở dữ liệu thử nghiệm, HTTP client với mock server, transaction. |
| End-to-end test | Một luồng nghiệp vụ đi qua các thành phần chính của ứng dụng. | Tạo đơn hàng, thanh toán thử nghiệm và xác nhận trạng thái cuối. |

Unit test nên chạy nhanh và ít phụ thuộc môi trường. Integration test xác nhận ranh giới giữa các thành phần. End-to-end test xác nhận luồng người dùng quan trọng trong cấu hình gần với cách ứng dụng được triển khai.

JShell hữu ích nhất ở bước khám phá. Nó có thể gọi thử một phương thức hoặc lớp đã biên dịch, nhưng không tự cung cấp fixture, database cô lập, test lifecycle hay báo cáo kiểm thử tích hợp.

## 7. Quy trình làm việc kết hợp JShell và test suite

1. **Đặt câu hỏi nhỏ:** xác định chính xác biểu thức, API hoặc quy tắc đang cần kiểm tra.
2. **Thử trong JShell:** nhập dữ liệu đại diện, giá trị biên và một trường hợp lỗi. Quan sát kết quả hoặc exception.
3. **Làm thí nghiệm có thể lặp lại:** lưu snippet quan trọng thành tệp .jsh; chạy lại trong phiên mới để loại bỏ phụ thuộc vào trạng thái cũ.
4. **Chốt hành vi:** xác nhận quy tắc nghiệp vụ, kiểu dữ liệu, giới hạn và cách xử lý lỗi trước khi đưa vào mã chính.
5. **Viết unit test:** chuyển các trường hợp quan trọng thành test có tên rõ ràng và assertion cụ thể.
6. **Bổ sung integration hoặc end-to-end test:** khi hành vi phụ thuộc vào cơ sở dữ liệu, mạng, cấu hình, nhiều module hoặc luồng người dùng.
7. **Chạy build và test suite:** kiểm tra từ trạng thái dự án sạch và để CI thực thi lại cùng bộ kiểm thử.

Nếu JShell phát hiện một lỗi, hãy tạo một thí nghiệm nhỏ tái hiện lỗi, sau đó chuyển trường hợp đó thành test hồi quy. Khi sửa xong, test hồi quy phải tiếp tục chạy đạt ở những lần build sau.

## 8. Những nhầm lẫn thường gặp

- **Nhầm một snippet chạy được với ứng dụng đã được kiểm thử.** Snippet chỉ xác nhận phần mã được chạy trong phiên hiện tại.
- **Dựa vào trạng thái phiên cũ.** Một biến hoặc import có thể đã được khai báo trước đó; hãy thử lại từ phiên mới.
- **Chỉ kiểm tra dữ liệu thuận lợi.** Cần xem cả giá trị rỗng, biên, không hợp lệ và lỗi từ phụ thuộc.
- **Chỉ nhìn kết quả in ra.** Trong test tự động, assertion phải xác nhận kết quả mong đợi; dòng log không tự làm test thất bại khi kết quả sai.
- **Không đưa lỗi đã tìm thấy vào bộ test.** Nếu lỗi không có test hồi quy, nó có thể xuất hiện trở lại.
- **Bỏ qua build và test của dự án.** Việc gọi được một lớp từ JShell không xác nhận package, module, tài nguyên hoặc các thành phần còn lại.

JShell giúp rút ngắn vòng lặp khám phá và làm rõ hành vi của một đoạn Java nhỏ. Unit test, integration test và end-to-end test biến những hành vi đã xác nhận thành bằng chứng có thể chạy lặp lại cho ứng dụng. Hãy dùng JShell để tìm hiểu nhanh, rồi đưa các quy tắc quan trọng vào bộ kiểm thử chính thức trước khi dựa vào chúng trong ứng dụng.