# Đọc since, exception contract và đặc tính API trước khi thay mã tiện ích riêng

Một phương thức trong thư viện chuẩn có tên giống hàm tiện ích nội bộ chưa chắc thay thế được nó. Trước khi xóa mã tự viết, cần kiểm tra API xuất hiện từ phiên bản Java nào, chữ ký và kiểu trả về, điều kiện đầu vào, exception có thể phát sinh, cùng các trường hợp biên như overflow, NaN và signed zero. Tài liệu Java SE mô tả các điểm này qua phần khai báo phương thức, nhãn **Since**, **Parameters**, **Returns**, **Throws** và phần mô tả chi tiết.

Trong Java 21, **Math.clamp()** và **StrictMath.clamp()** là ví dụ rõ ràng về API mới có thể thay một số hàm giới hạn giá trị tự viết. Tuy nhiên, chỉ thay khi hợp đồng của hàm cũ trùng với hợp đồng của API mới. Với phép cộng cần phát hiện overflow, **Math.addExact()** có hợp đồng khác toán tử cộng thông thường; với chuyển long sang int, **Math.toIntExact()** khác cách chuyển bão hòa bằng clamp.

## 1. Đọc tài liệu API theo một thứ tự cố định

Khi mở Javadoc của một phương thức, hãy đọc các phần sau trước khi quyết định thay mã:

1. **Khai báo và overload**: xác định kiểu tham số, kiểu trả về, generic type nếu có và overload nào được chọn.
2. **Since**: xác định phiên bản Java đầu tiên có API.
3. **Parameters**: hiểu ý nghĩa và điều kiện của từng tham số.
4. **Returns**: xác định chính xác kết quả, bao gồm trường hợp đặc biệt.
5. **Throws**: kiểm tra exception, điều kiện phát sinh và việc caller hiện tại có xử lý được hay không.
6. **Mô tả chi tiết**: đọc quy tắc số học, thứ tự, độ chính xác, overflow, NaN, signed zero và các bảo đảm khác.

Không dừng ở tên phương thức hoặc một ví dụ đơn giản. Hai hàm cùng trả về một số trong trường hợp thông thường vẫn có thể khác nhau khi nhận giá trị biên hoặc dữ liệu không hợp lệ.

## 2. Ý nghĩa của Since trong Java API

Trong Javadoc, **Since** cho biết phiên bản Java mà API được bổ sung. Ví dụ:

| API | Phiên bản xuất hiện |
|---|---:|
| **Math.addExact(int, int)** | Java 8 |
| **Math.toIntExact(long)** | Java 8 |
| **Math.floorDiv(int, int)** | Java 8 |
| **Math.floorDivExact(long, long)** | Java 18 |
| **Math.clamp(long, int, int)** | Java 21 |
| **Math.clamp(long, long, long)** | Java 21 |
| **Math.clamp(float, float, float)** | Java 21 |
| **Math.clamp(double, double, double)** | Java 21 |

Khi dự án yêu cầu Java 21, có thể dùng các API có Since không lớn hơn 21. Nếu một thư viện cần chạy trên Java 17 hoặc thấp hơn, không thể gọi trực tiếp Math.clamp() chỉ vì mã nguồn được biên dịch trên máy có JDK 21; cần giữ cách triển khai tương thích hoặc nâng phiên bản runtime tối thiểu của ứng dụng.

Phân biệt ba mốc:

- **JDK dùng để biên dịch**: bộ công cụ javac thực hiện compilation.
- **Release/API target**: tập API và cú pháp mà mã được phép sử dụng khi biên dịch, ví dụ tùy chọn **--release 21**.
- **Runtime tối thiểu**: phiên bản JVM thực tế phải có để chạy ứng dụng.

Biên dịch thành công bằng JDK mới mà không đặt release phù hợp không chứng minh ứng dụng còn tương thích với runtime cũ. Khi thay một utility bằng API mới, hãy kiểm tra chính sách Java tối thiểu của sản phẩm.

## 3. Đọc chữ ký và overload trước khi thay thế

Tên phương thức có thể giống nhau nhưng overload quyết định kiểu đầu vào và kiểu trả về. Trong Java 21, Math và StrictMath có bốn overload clamp:

| Chữ ký | Kiểu trả về | Ý nghĩa |
|---|---|---|
| **clamp(long value, int min, int max)** | int | Giới hạn long vào khoảng có hai cận int |
| **clamp(long value, long min, long max)** | long | Giới hạn long vào khoảng long |
| **clamp(float value, float min, float max)** | float | Giới hạn float |
| **clamp(double value, double min, double max)** | double | Giới hạn double |

Không có overload riêng **clamp(int, int, int)**. Khi truyền ba đối số int, compiler mở rộng đối số đầu sang long và chọn overload **clamp(long, int, int)**, trả về int.

~~~java
class OverloadSelection {
    static int limitPage(int page) {
        // Chọn clamp(long, int, int), kết quả vẫn là int.
        return Math.clamp(page, 1, 500);
    }

    static int limitImportedValue(long value) {
        // Chọn overload long,int,int để giới hạn rồi trả về int.
        return Math.clamp(value, 0, 10_000);
    }

    static long limitLong(long value) {
        return Math.clamp(value, 0L, 10_000L);
    }
}
~~~

Khi thay utility, kiểm tra cả kiểu trả về ở các caller. Một thay đổi overload có thể làm thay đổi kiểu biểu thức, phép overload resolution ở lời gọi tiếp theo hoặc việc gán vào biến.

## 4. Đọc exception contract, không chỉ đọc kiểu trả về

Phần **Throws** trong Javadoc mô tả các điều kiện mà phương thức có thể ném exception. Nhiều API số học ném unchecked exception; chữ ký Java không bắt buộc caller phải khai báo hoặc bắt chúng, nhưng hành vi này vẫn là một phần hợp đồng.

| API | Điều kiện | Exception |
|---|---|---|
| **Math.clamp(value, min, max)** với kiểu nguyên | min lớn hơn max | IllegalArgumentException |
| **Math.clamp(value, min, max)** với float/double | Cận không hợp lệ, gồm NaN hoặc khoảng sai | IllegalArgumentException |
| **Math.addExact(a, b)** | Kết quả vượt miền biểu diễn của kiểu | ArithmeticException |
| **Math.toIntExact(value)** | long không biểu diễn được bằng int | ArithmeticException |
| **Math.floorDiv(a, 0)** | Số chia bằng 0 | ArithmeticException |

Khi thay hàm cũ bằng API chuẩn, kiểm tra caller có đang dựa vào hành vi khác không. Ví dụ, hàm cũ có thể trả về giá trị mặc định khi tham số sai, trong khi API chuẩn ném exception. Đây là thay đổi hành vi quan sát được và có thể ảnh hưởng tới giao thức hoặc xử lý lỗi của ứng dụng.

## 5. Ví dụ thay hàm clamp tự viết bằng Math.clamp

Giả sử dự án có hàm giới hạn một giá trị int:

~~~java
class LegacyRange {
    static int clamp(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
        return Math.max(min, Math.min(value, max));
    }
}
~~~

Với hợp đồng trên, Java 21 có thể dùng Math.clamp():

~~~java
class PageRange {
    static int normalizePage(int requestedPage) {
        return Math.clamp(requestedPage, 1, 500);
    }
}
~~~

Trước khi xóa hàm cũ, xác nhận:

- Khoảng có bao gồm cả min và max hay không.
- min lớn hơn max có ném IllegalArgumentException giống nhau hay không.
- Hàm cũ có đổi chỗ hai cận hoặc tự sửa cận không.
- Có overload số thực không và chúng xử lý NaN, signed zero như thế nào.
- Caller có phụ thuộc vào kiểu trả về hoặc exception cụ thể không.

Nếu hàm cũ cố ý đổi chỗ cận khi min lớn hơn max, thay trực tiếp bằng Math.clamp sẽ thay đổi hợp đồng. Cần quyết định giữ quy tắc nghiệp vụ đó trong một lớp kiểm tra riêng hay sửa caller để cung cấp cận hợp lệ.

## 6. Đặc tính số thực: NaN, vô cực và signed zero

Với **Math.clamp(float/double)**, đọc phần mô tả chi tiết vì các giá trị đặc biệt có ảnh hưởng đến kết quả:

- Nếu value là NaN, kết quả là NaN.
- Nếu min hoặc max là NaN, phương thức ném IllegalArgumentException.
- Nếu min lớn hơn max, phương thức ném IllegalArgumentException.
- Cặp min = +0.0 và max = -0.0 không hợp lệ.
- Khi cận dưới là +0.0 và value là -0.0, kết quả là +0.0.
- Với cận hữu hạn, âm vô cực bị giới hạn về min và dương vô cực bị giới hạn về max.

~~~java
class FloatingPointContract {
    static double normalize(double value) {
        return Math.clamp(value, 0.0, 1.0);
    }

    public static void main(String[] args) {
        System.out.println(normalize(-0.5)); // 0.0
        System.out.println(normalize(0.4));  // 0.4
        System.out.println(normalize(2.0));  // 1.0

        double result = normalize(Double.NaN);
        System.out.println(Double.isNaN(result)); // true
    }
}
~~~

Nếu utility cũ chuyển NaN thành 0 hoặc từ chối mọi giá trị không hữu hạn, không thể thay trực tiếp bằng clamp mà không giữ thêm validation. Dùng **Double.isNaN()** khi chỉ muốn từ chối NaN; dùng **Double.isFinite()** nếu cả NaN và hai giá trị vô cực đều không hợp lệ.

## 7. Phân biệt giới hạn bão hòa và kiểm tra overflow

Hai mục tiêu thường bị nhầm:

- **Saturating conversion**: giá trị vượt cận được đưa về cận gần nhất.
- **Checked arithmetic**: phép tính vượt miền biểu diễn thì báo lỗi.

Java 21 cung cấp các API cho cả hai kiểu hợp đồng:

~~~java
class OverflowContracts {
    static int saturateToInt(long value) {
        return Math.clamp(
                value,
                Integer.MIN_VALUE,
                Integer.MAX_VALUE
        );
    }

    static int requireInt(long value) {
        return Math.toIntExact(value);
    }

    static int addChecked(int left, int right) {
        return Math.addExact(left, right);
    }
}
~~~

Với saturateToInt, long quá lớn trả về Integer.MAX_VALUE và long quá nhỏ trả về Integer.MIN_VALUE. Với requireInt, giá trị nằm ngoài miền int ném ArithmeticException. Với addChecked, phép cộng int overflow cũng ném ArithmeticException thay vì âm thầm wrap quanh miền số nguyên.

Chọn API theo quy tắc nghiệp vụ. Không thay một hàm đang báo lỗi overflow bằng clamp nếu việc đưa kết quả về cận sẽ che giấu dữ liệu sai. Ngược lại, không dùng toIntExact nếu sản phẩm chủ ý cần chuyển đổi bão hòa.

## 8. Đọc đặc tính của phép chia và modulo

Tên divide hoặc toán tử / không luôn tương đương với floor division. Phép chia số nguyên / của Java cắt phần thập phân về 0. **Math.floorDiv()** làm tròn thương về âm vô cực; **Math.floorMod()** trả về phần dư tương ứng với phép chia floor.

~~~java
class DivisionContracts {
    public static void main(String[] args) {
        System.out.println(-7 / 3);                 // -2
        System.out.println(Math.floorDiv(-7, 3));  // -3
        System.out.println(-7 % 3);                // -1
        System.out.println(Math.floorMod(-7, 3));  // 2
    }
}
~~~

Nếu utility cũ dùng / và %, thay bằng floorDiv/floorMod sẽ làm thay đổi kết quả với số âm. Đây có thể là điều đúng khi tính bucket theo trục số, lịch hoặc khoảng thời gian, nhưng phải được xác nhận theo yêu cầu nghiệp vụ.

Các overload floorDiv/floorMod ném ArithmeticException khi số chia bằng 0. Với floorDiv(long, long), trường hợp Long.MIN_VALUE chia cho -1 bị overflow và kết quả là Long.MIN_VALUE; phương thức không ném ArithmeticException cho trường hợp overflow này. Nếu utility cũ yêu cầu báo lỗi khi thương không biểu diễn được, hãy xem **Math.floorDivExact(long, long)** (Since Java 18) thay vì thay trực tiếp bằng floorDiv.

## 9. Kiểm tra đặc tính API ngoài kết quả thông thường

Ngoài Since và Throws, khi thay utility cần đọc những đặc tính sau:

| Đặc tính | Câu hỏi cần trả lời |
|---|---|
| Kiểu số | API nhận int, long, float, double hay kiểu khác? |
| Miền giá trị | Có hỗ trợ giá trị âm, cực trị, NaN và vô cực không? |
| Overflow | Wrap quanh, bão hòa hay ném exception? |
| Rounding | Cắt về 0, floor, ceiling hay round theo quy tắc khác? |
| Độ chính xác | Có bảo đảm sai số hoặc kết quả bit-for-bit không? |
| Side effect | Có thay đổi đối tượng đầu vào hay trạng thái dùng chung không? |
| Nullability | Có tham số tham chiếu nào có thể null không? |
| Mutability | Kết quả là object mới, view hay đối tượng có thể sửa? |
| Compatibility | API có tồn tại trong Java release tối thiểu của sản phẩm không? |

Đối với Math và StrictMath, kiểm tra thêm yêu cầu về tính nhất quán kết quả. Không chuyển từ Math sang StrictMath hoặc ngược lại chỉ dựa vào tên; hãy xem hợp đồng của đúng phương thức và yêu cầu reproducibility của ứng dụng.

## 10. Quy trình thay utility riêng bằng API chuẩn

Thực hiện theo trình tự sau để tránh thay tên phương thức nhưng vô tình đổi semantics:

1. Tìm toàn bộ khai báo utility cũ và các caller.
2. Viết lại hợp đồng hiện tại: miền đầu vào, kết quả, exception, overflow và trường hợp biên.
3. Mở Javadoc của API chuẩn trong đúng phiên bản Java mục tiêu.
4. Xác nhận Since không vượt quá runtime tối thiểu của sản phẩm.
5. So sánh overload, kiểu trả về và exception contract.
6. So sánh hành vi với NaN, signed zero, giá trị cực trị và số âm nếu áp dụng.
7. Tạo test thể hiện hợp đồng cũ và các khác biệt có chủ đích.
8. Thay caller, chạy kiểm tra tương thích và quan sát log/metric nếu thay đổi exception behavior.
9. Xóa utility cũ chỉ khi không còn caller và hợp đồng mới đã được chấp nhận.

Nếu hai hợp đồng không giống nhau, có thể giữ một adapter nhỏ bao quanh API chuẩn để bảo toàn quy tắc của ứng dụng. Mục tiêu là giảm mã tự triển khai nhưng vẫn giữ hành vi đã được xác định.

## 11. Ví dụ bảng quyết định thay thế

| Utility tự viết đang làm gì? | API Java 21 có thể xem xét | Điều phải xác minh |
|---|---|---|
| Giới hạn giá trị trong khoảng đóng | **Math.clamp()** | Cận hợp lệ, NaN, signed zero và kiểu overload |
| Chuyển long sang int theo kiểu bão hòa | **Math.clamp(long, int, int)** | Cận int và chính sách cho giá trị vượt miền |
| Chuyển long sang int nhưng báo lỗi khi vượt miền | **Math.toIntExact()** | Caller xử lý ArithmeticException |
| Cộng số nguyên và phát hiện overflow | **Math.addExact()** | Exception thay cho wraparound |
| Chia số nguyên theo floor | **Math.floorDiv()** | Kết quả khi có số âm và số chia bằng 0 |
| Tính modulo tương ứng với floor division | **Math.floorMod()** | Dấu của phần dư và trường hợp số chia bằng 0 |

Các API trong bảng không thay thế lẫn nhau. Chọn theo ý nghĩa phép toán mà utility cũ đang cung cấp.

## 12. Checklist đọc Javadoc trước khi refactor

- [ ] Đọc đúng tài liệu của phiên bản Java mục tiêu.
- [ ] Kiểm tra **Since** và runtime tối thiểu được hỗ trợ.
- [ ] Chọn đúng overload và xác nhận kiểu trả về.
- [ ] Đọc **Parameters**, **Returns** và **Throws**.
- [ ] Kiểm tra overflow, rounding và miền giá trị.
- [ ] Với số thực, kiểm tra NaN, vô cực và signed zero.
- [ ] So sánh hành vi với utility cũ ở cả trường hợp thông thường và biên.
- [ ] Xác định thay đổi exception có ảnh hưởng caller hay không.
- [ ] Thêm test cho hợp đồng mới trước khi xóa mã cũ.
- [ ] Chỉ loại bỏ utility khi không còn khác biệt nghiệp vụ cần giữ.

## Tài liệu tham khảo

- [Java SE 21 API: Math](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
- [Java SE 21 API: StrictMath](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StrictMath.html)
- [Java SE 21 API: Double](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html)
- [Java SE 21 API: Float](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Float.html)
- [Java SE 21 javac documentation: --release](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
