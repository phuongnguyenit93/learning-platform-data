# Kiến thức tiên quyết và trình tự học đề xuất — Java Core: Numbers

## 1. Bài này dành cho ai?

Đây là **bản đồ chuẩn bị và tự học** dành cho người đã biết cú pháp Java căn bản nhưng chưa chắc nên bắt đầu từ đâu khi gặp bài toán số. Mục đích là đánh giá điểm xuất phát, định thứ tự luyện tập và biết quay lại phần thích hợp khi sai; các bài đứng trước cung cấp giải thích sâu về từng kiểu và phép tính.

Bạn cần một JDK 17 trở lên để chạy ví dụ, biết tạo class có `main`, khai báo biến, dùng biểu thức, gọi phương thức, xử lý ngoại lệ và đọc output terminal. Chưa cần biết Spring, đa luồng hay chi tiết bộ nhớ JVM.

## 2. Kiểm tra kiến thức tiên quyết

| Nền tảng | Phải làm được | Nếu chưa đạt |
| --- | --- | --- |
| JDK và terminal | Chạy `javac File.java` rồi `java File` | Ôn trình biên dịch, classpath và tệp Java |
| Biến, literal, toán tử | Dự đoán `2 + 3 * 4` và `(2 + 3) * 4` | Ôn thứ tự toán tử và dấu ngoặc |
| Kiểu dữ liệu, chuyển kiểu | Phân biệt `int`, `double`, cast trước/sau chia | Ôn kiểu toán hạng và phép gán |
| Phương thức và `import` | Gọi `Math.max(2, 3)` | Ôn cách gọi static method |
| Rẽ nhánh, vòng lặp | Kiểm tra giá trị âm, lặp qua nhiều input | Ôn điều kiện, phép so sánh |
| Ngoại lệ | Dùng `try/catch` khi parse sai hoặc chia nguyên cho 0 | Ôn `NumberFormatException`, `ArithmeticException` |

### Bài kiểm tra đầu vào có thể tự chạy

Tạo `NumbersPrerequisiteCheck.java`:

```java
public class NumbersPrerequisiteCheck {
    public static void main(String[] args) {
        int items = 7;
        int groups = 2;
        System.out.println(items / groups);
        System.out.println((double) items / groups);
        System.out.println(2 + 3 * 4);
        System.out.println((2 + 3) * 4);
    }
}
```

```bash
javac NumbersPrerequisiteCheck.java
java NumbersPrerequisiteCheck
```

Kết quả:

```text
3
3.5
14
20
```

Nếu kết quả sai dự đoán, giải thích **kiểu tại lúc phép toán diễn ra** và thứ tự ưu tiên trước khi chạy lại. Đây là bài kiểm tra kỹ năng Java nền tảng, không phải bài kiểm tra thuộc lòng bảng miền giá trị.

## 3. Trình tự học tám bài của chương

Menu của chương bắt đầu bằng tình huống thực tế, chuyển sang cơ chế, rồi kết thúc bằng việc dùng JDK đúng phiên bản. Đi theo thứ tự dưới đây khi học lần đầu; nếu đã biết một phần, có thể dùng cột tự kiểm tra để chọn nơi ôn.

| Chặng | Bài trong chương | Câu hỏi tự kiểm tra trước khi đi tiếp |
| --- | --- | --- |
| 1 | Số trong Java là gì và những bài toán cần biểu diễn | Giải thích vì sao mã `"00123"` khác số lượng 123 và giá 123.00 |
| 2 | Phân biệt giá trị toán học, kiểu dữ liệu và cách lưu trữ | Phân tách giá trị, kiểu, bit lưu và chuỗi hiển thị |
| 3 | Số nguyên, số dấu phẩy động và số thập phân chính xác | Dự đoán hành vi chia nguyên, số thực và BigDecimal |
| 4 | Phạm vi giá trị khác độ chính xác như thế nào | Phân biệt overflow với mất độ phân giải ở số thực |
| 5 | Bản đồ primitive, wrapper, Number, BigInteger và BigDecimal | Biết tại sao unboxing null gây lỗi và Number không có toán tử cộng chung |
| 6 | Chọn kiểu theo ý nghĩa dữ liệu và yêu cầu tính toán | Lý giải lựa chọn kiểu cho hóa đơn, bộ đếm, cảm biến và API |
| 7 | Kiến thức tiên quyết và trình tự học đề xuất | Tự đánh giá điểm yếu và lập kế hoạch ôn phần cần thiết |
| 8 | Phạm vi Java Core và cách đối chiếu phiên bản JDK | Kiểm tra xem phương thức có trong Java 17 hay chỉ ra đời ở Java 21 |

**Cách sử dụng bản đồ:** Sau chặng 2, thử tự giải thích một số được hiển thị khác với bit biểu diễn. Sau chặng 3–4, thử tính `0.1 + 0.2` và cộng `1` vào `1e16` để xem sự khác nhau giữa lỗi biểu diễn và độ phân giải. Chặng 5 giúp đọc API nhận `Number`; chặng 6 yêu cầu ra quyết định có hợp đồng dữ liệu; chặng 8 kiểm chứng tương thích khi chuyển dự án sang JDK khác.

## 4. Luyện tập có thứ tự

### Bài A — Đọc biểu thức trước khi chạy

Với `int a = 9, b = 4;`, dự đoán `a / b`, `a % b`, `(double) a / b` và `(double) (a / b)`. Tự xác minh output lần lượt là `2`, `1`, `2.25`, `2.0`. Nếu sai, ôn **chặng 2–3**; nguyên nhân là kiểu toán hạng và thời điểm cast.

### Bài B — Xác định loại sai số

Chạy `Integer.MAX_VALUE + 1`, `16777216f + 1 == 16777216f` và `0.1 + 0.2 == 0.3`. Ba biểu thức lần lượt minh họa tràn số nguyên, độ phân giải float và làm tròn nhị phân. Giải thích sự khác nhau trước khi chọn `Math.addExact`, thay kiểu số hoặc dùng decimal chính xác. Nếu nhầm lẫn, ôn **chặng 3–4**.

### Bài C — Từ yêu cầu đến kiểu dữ liệu

Một đơn hàng có mã `"000045"`, số lượng 3, giá `"19.95"`, thuế 8% và tổng dung lượng xử lý vượt 4 tỷ byte. Hãy đề xuất kiểu Java và xác định:

1. Trường nào là mã định danh, trường nào là đại lượng để tính?
2. Phép toán trung gian nào có thể tràn nếu hai toán hạng đều là `int`?
3. Phải thống nhất scale, đơn vị tiền tệ, `RoundingMode` và thời điểm làm tròn tại đâu?
4. JSON/client và database có giữ nguyên giá trị, đơn vị và các số 0 đầu không?

Nếu không bảo vệ được quyết định, quay về **chặng 5–6**.

### Bài D — Kiểm tra tương thích JDK

Dùng tài liệu API đúng bản phát hành tìm `Math.addExact`, `NumberFormat.getCompactNumberInstance` và `Math.clamp`. Biên dịch ví dụ thích hợp với `javac --release 17`, phân biệt thiếu API với lỗi cú pháp. Nếu chưa biết compiler, runtime và `--release` khác nhau thế nào, ôn **chặng 8**.

## 5. Cách tự học và ghi bằng chứng

Ở mỗi chặng, ghi một bảng ngắn gồm *dự đoán → phép thử → output thật → nguyên nhân → bài cần ôn*. Với phép đo, thử `NaN` và giới hạn sai số; với số nguyên, thử cực trị và phép toán trung gian; với tiền, thử các giá trị ở điểm giữa cần làm tròn; với wrapper, thử `null` tại unboxing. Mục tiêu là giải thích được **vì sao** một kết quả xảy ra và **khi nào** cách xử lý còn phù hợp.

Đánh dấu hoàn thành sau khi tự kiểm tra:

- [ ] Biên dịch/chạy được các ví dụ Numbers độc lập và đọc được lỗi biên dịch so với ngoại lệ runtime.
- [ ] Dự đoán kiểu toán hạng của chia nguyên, promotion, cast và gán kết quả.
- [ ] Nhận biết overflow và dùng `Math.*Exact` ở đúng phép toán nếu cần kiểm tra.
- [ ] Phân biệt range, precision và sai số do biểu diễn floating-point.
- [ ] Giải thích primitive, wrapper, `Number`, `BigInteger`, `BigDecimal` và rủi ro `null`.
- [ ] Chọn kiểu theo miền, đơn vị, phép toán và yêu cầu decimal/rounding cụ thể.
- [ ] Xác minh bảo toàn dữ liệu qua JSON, database, định dạng và locale.
- [ ] Biết tìm đúng phiên bản API và kiểm chứng `javac --release` trên runtime đích.

**Khi đã đạt:** chuyển sang các bài toán API số nâng cao trong module. Nếu còn mục chưa hoàn thành, quay lại đúng chặng và tự tạo một phép thử biên mới; không cần học lại toàn chương chỉ vì một sai lầm nhỏ.
