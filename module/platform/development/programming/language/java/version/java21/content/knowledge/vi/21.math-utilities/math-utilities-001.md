# Math.clamp và StrictMath.clamp để giới hạn giá trị trong khoảng

Java 21 bổ sung **Math.clamp()** và **StrictMath.clamp()** để giới hạn một giá trị trong khoảng từ cận dưới đến cận trên. Nếu giá trị nhỏ hơn cận dưới, phương thức trả về cận dưới; nếu lớn hơn cận trên, phương thức trả về cận trên; nếu đã nằm trong khoảng, phương thức giữ nguyên giá trị.

Hai API này hữu ích khi giới hạn phần trăm, âm lượng, kích thước trang, điểm số hoặc khi chuyển một giá trị **long** sang **int** theo kiểu bão hòa (saturating conversion). Cần hiểu đúng kiểu overload và các trường hợp biên như khoảng không hợp lệ, NaN và signed zero.

## 1. Cú pháp và cách hoạt động

Các phương thức có ba tham số:

- **value**: giá trị cần giới hạn.
- **min**: cận dưới được phép.
- **max**: cận trên được phép.

Khoảng được xét bao gồm cả hai đầu mút. Có thể mô tả kết quả bằng quy tắc:

- Nếu value nhỏ hơn min, kết quả là min.
- Nếu value lớn hơn max, kết quả là max.
- Nếu value nằm trong khoảng min đến max, kết quả là value.

Ví dụ:

~~~java
class ClampBasics {
    public static void main(String[] args) {
        int low = Math.clamp(-5, 0, 100);
        int normal = Math.clamp(42, 0, 100);
        int high = Math.clamp(150, 0, 100);

        System.out.println(low);    // 0
        System.out.println(normal); // 42
        System.out.println(high);   // 100
    }
}
~~~

Giá trị bằng min hoặc max được giữ nguyên. Nếu min và max bằng nhau, mọi giá trị hợp lệ đều cho kết quả bằng cận đó.

## 2. Các overload trong Java 21

Math và StrictMath đều cung cấp cùng bốn chữ ký:

| Chữ ký | Kiểu trả về | Mục đích |
|---|---|---|
| **clamp(long value, int min, int max)** | int | Giới hạn long trong khoảng có cận int; có thể dùng để chuyển long sang int an toàn |
| **clamp(long value, long min, long max)** | long | Giới hạn giá trị long trong khoảng long |
| **clamp(float value, float min, float max)** | float | Giới hạn giá trị float |
| **clamp(double value, double min, double max)** | double | Giới hạn giá trị double |

Tất cả các overload trên được thêm từ Java 21. Không có chữ ký riêng **clamp(int value, int min, int max)**. Khi truyền ba đối số int, Java có thể mở rộng đối số value sang long và chọn overload trả về int.

~~~java
class ClampOverloads {
    static int clampInt(int value) {
        // Chọn clamp(long, int, int); kết quả là int.
        return Math.clamp(value, 0, 100);
    }

    static long clampLong(long value) {
        return Math.clamp(value, -1_000L, 1_000L);
    }

    static float clampFloat(float value) {
        return Math.clamp(value, 0.0f, 1.0f);
    }

    static double clampDouble(double value) {
        return Math.clamp(value, 0.0, 1.0);
    }
}
~~~

Hãy giữ đúng kiểu dữ liệu của cận. Hậu tố L làm literal có kiểu long; hậu tố f làm literal có kiểu float. Nếu cần kết quả long, dùng cận long để trình biên dịch chọn overload long-long-long.

## 3. Dùng clamp(long, int, int) để chuyển long sang int an toàn

Overload **clamp(long value, int min, int max)** đặc biệt hữu ích khi dữ liệu đầu vào có kiểu long nhưng API đích chỉ nhận int. Kết quả luôn nằm trong khoảng int do caller cung cấp, vì vậy không bị tràn khi thu hẹp kiểu.

~~~java
class SaturatingConversion {
    static int toIntSaturated(long value) {
        return Math.clamp(
                value,
                Integer.MIN_VALUE,
                Integer.MAX_VALUE
        );
    }

    public static void main(String[] args) {
        long importedValue = 3_500_000_000L;

        int safeValue = toIntSaturated(importedValue);
        System.out.println(safeValue); // 2147483647
    }
}
~~~

Nếu giá trị long vượt quá Integer.MAX_VALUE, kết quả bằng Integer.MAX_VALUE; nếu nhỏ hơn Integer.MIN_VALUE, kết quả bằng Integer.MIN_VALUE. Giá trị nằm trong miền int được giữ nguyên.

Không ép kiểu trước rồi mới giới hạn:

~~~java
long value = 3_500_000_000L;

int truncated = (int) value; // Mất các bit cao; kết quả không phải giới hạn bão hòa.
int safe = Math.clamp(value, Integer.MIN_VALUE, Integer.MAX_VALUE);
~~~

Ép kiểu thu hẹp long sang int không tự giới hạn ở hai biên int. Hãy gọi clamp trên giá trị long ban đầu để tránh mất dữ liệu trước khi kiểm tra khoảng.

## 4. Ứng dụng với dữ liệu giao diện và cấu hình

Một trường hợp phổ biến là giới hạn giá trị phần trăm hoặc âm lượng trong khoảng 0 đến 100:

~~~java
class PlayerSettings {
    private int volume;

    void setVolume(int requestedVolume) {
        volume = Math.clamp(requestedVolume, 0, 100);
    }

    int volume() {
        return volume;
    }
}
~~~

Nếu giao diện gửi -10, âm lượng được đặt thành 0. Nếu gửi 130, âm lượng được đặt thành 100. Nếu gửi 65, giá trị 65 được giữ nguyên.

Clamp chỉ giới hạn giá trị theo khoảng số học. Nó không kiểm tra quyền truy cập, không xác thực dữ liệu nghiệp vụ khác và không thay thế validation cho những điều kiện như đơn hàng có tồn tại hay người dùng có quyền thay đổi cấu hình.

## 5. Giới hạn số thực float và double

Với số thực, dùng đúng overload tương ứng để giữ kiểu dữ liệu:

~~~java
class FloatingPointClamp {
    static float normalizeOpacity(float opacity) {
        return Math.clamp(opacity, 0.0f, 1.0f);
    }

    static double normalizeProgress(double progress) {
        return Math.clamp(progress, 0.0, 1.0);
    }

    public static void main(String[] args) {
        System.out.println(normalizeOpacity(-0.2f)); // 0.0
        System.out.println(normalizeOpacity(0.6f));  // 0.6
        System.out.println(normalizeProgress(1.4));  // 1.0
    }
}
~~~

Các giá trị âm vô cực và dương vô cực được so sánh với cận như những giá trị số thông thường. Với cận hữu hạn, âm vô cực được giới hạn về min và dương vô cực được giới hạn về max.

Clamp không làm tròn số, không chuyển đơn vị và không thay NaN thành một giá trị mặc định. Nếu chỉ cần từ chối NaN, hãy kiểm tra bằng **Float.isNaN()** hoặc **Double.isNaN()**. Nếu chỉ chấp nhận số hữu hạn, dùng **Float.isFinite()** hoặc **Double.isFinite()** để loại cả NaN và hai giá trị vô cực.

## 6. Các trường hợp NaN và signed zero

Overload float và double có các quy tắc cần nhớ:

| Đầu vào hoặc cận | Hành vi |
|---|---|
| value là NaN | Kết quả là NaN |
| min là NaN | Ném IllegalArgumentException |
| max là NaN | Ném IllegalArgumentException |
| min lớn hơn max | Ném IllegalArgumentException |
| min là +0.0 và max là -0.0 | Ném IllegalArgumentException |
| value là -0.0, cận dưới là +0.0 | Trả về +0.0 |

Java xem **-0.0** nhỏ hơn **+0.0** trong phép so sánh của clamp. Điều này khác với toán tử so sánh số học thông thường ở chỗ **-0.0 == +0.0** cho kết quả true.

~~~java
class ClampFloatingPointEdges {
    public static void main(String[] args) {
        double value = Math.clamp(-0.0, 0.0, 1.0);

        System.out.println(value); // 0.0
        System.out.println(
                Double.doubleToRawLongBits(value)
                        == Double.doubleToRawLongBits(0.0)
        ); // true: kết quả là positive zero

        double notANumber = Math.clamp(Double.NaN, 0.0, 1.0);
        System.out.println(Double.isNaN(notANumber)); // true
    }
}
~~~

Nếu dữ liệu đến từ phép tính có thể tạo NaN, đừng mặc định clamp sẽ đưa nó về min hoặc max. Kết quả NaN có thể tiếp tục lan sang các phép tính sau.

## 7. Khoảng không hợp lệ sẽ ném exception

Điều kiện hợp lệ là **min <= max** theo quy tắc của overload tương ứng. Clamp không tự đổi chỗ hai cận khi caller truyền sai thứ tự.

~~~java
class InvalidClampRange {
    static int limit(int value, int min, int max) {
        return Math.clamp(value, min, max);
    }

    public static void main(String[] args) {
        limit(50, 100, 0); // Ném IllegalArgumentException
    }
}
~~~

Với float và double, ngoài điều kiện min không lớn hơn max, hai cận cũng không được là NaN. Cặp cận **min = +0.0** và **max = -0.0** cũng không hợp lệ.

Nếu cận được cấu hình từ file hoặc request, hãy xác thực chúng tại ranh giới đầu vào và báo lỗi cấu hình rõ ràng. Không nên bắt IllegalArgumentException rồi âm thầm đổi thứ tự cận, vì hành vi đó có thể che giấu lỗi cấu hình.

## 8. Math.clamp và StrictMath.clamp

Cả **Math** và **StrictMath** đều có cùng bốn overload clamp trong Java 21 và cùng quy tắc giới hạn khoảng, xử lý NaN, signed zero và cận không hợp lệ.

- Dùng **Math.clamp()** trong mã ứng dụng thông thường; đây là lựa chọn trực tiếp và dễ nhận biết cho thao tác số học.
- Dùng **StrictMath.clamp()** nếu codebase có quy ước sử dụng StrictMath nhất quán cho các phép toán số học.

StrictMath có các yêu cầu kết quả bit-for-bit giống nhau giữa các implementation đối với một số hàm toán học được chỉ định. Clamp chỉ chọn một trong các giá trị đầu vào theo điều kiện so sánh, và hai class công bố cùng hợp đồng cho thao tác này. Không cần chuyển toàn bộ mã từ Math sang StrictMath chỉ để giới hạn một giá trị.

~~~java
class CompareClampApis {
    public static void main(String[] args) {
        double value = 125.0;

        double mathResult = Math.clamp(value, 0.0, 100.0);
        double strictResult = StrictMath.clamp(value, 0.0, 100.0);

        System.out.println(mathResult);   // 100.0
        System.out.println(strictResult); // 100.0
    }
}
~~~

## 9. Khi nào không nên dùng clamp?

Clamp phù hợp khi muốn giữ một giá trị trong khoảng đóng. Nó không phải phép chuẩn hóa mọi dạng dữ liệu:

| Nhu cầu | Hướng xử lý |
|---|---|
| Giới hạn phần trăm trong 0..100 | Math.clamp(value, 0, 100) |
| Chuyển long sang int với giới hạn bão hòa | Math.clamp(value, Integer.MIN_VALUE, Integer.MAX_VALUE) |
| Kiểm tra đầu vào có phải số hữu hạn | Double.isFinite(value) hoặc Float.isFinite(value) |
| Chuẩn hóa góc theo chu kỳ 360 độ | Dùng phép modulo phù hợp; clamp sẽ giữ góc lớn nhất tại 360 thay vì quay về 0 |
| Làm tròn đến số nguyên | Dùng Math.round(), Math.floor() hoặc Math.ceil() theo yêu cầu |
| Giới hạn kiểu BigDecimal | So sánh và chọn cận bằng API BigDecimal; Math.clamp không có overload BigDecimal |

Không dùng clamp để che giấu dữ liệu không hợp lệ. Ví dụ, một số lượng âm có thể cần bị từ chối theo quy tắc nghiệp vụ thay vì tự động biến thành 0.

## 10. Checklist sử dụng clamp

- [ ] Xác định rõ cận dưới và cận trên của miền giá trị hợp lệ.
- [ ] Dùng đúng overload theo kiểu dữ liệu.
- [ ] Nhớ overload clamp(long, int, int) trả về int và hỗ trợ chuyển long sang int theo kiểu bão hòa.
- [ ] Không ép kiểu long sang int trước khi clamp.
- [ ] Bảo đảm min <= max.
- [ ] Với float/double, xử lý riêng NaN nếu nghiệp vụ không chấp nhận nó.
- [ ] Hiểu quy tắc signed zero của overload số thực.
- [ ] Chọn Math hoặc StrictMath theo quy ước của codebase.
- [ ] Không nhầm clamp với làm tròn, modulo hoặc validation nghiệp vụ.

## Tài liệu tham khảo

- [Java SE 21 API: Math](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
- [Java SE 21 API: StrictMath](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StrictMath.html)
- [Java SE 21 API: Float](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Float.html)
- [Java SE 21 API: Double](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html)
