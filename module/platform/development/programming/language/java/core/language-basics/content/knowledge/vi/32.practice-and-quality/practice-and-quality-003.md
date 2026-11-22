# Đặt tên rõ nghĩa, thụt lề và tránh số không giải thích trong Java

Mã dễ đọc giúp người khác hiểu **ý nghĩa và ý định** mà không phải đoán từ cách triển khai. Với Java 17+, ba thói quen có tác dụng trực tiếp là đặt tên thể hiện vai trò, định dạng khối lệnh nhất quán và thay các con số mang quy tắc nghiệp vụ bằng tên có nghĩa.

## 1. Đặt tên nói rõ dữ liệu và hành động

| Thành phần | Quy ước phổ biến trong Java | Ví dụ |
| --- | --- | --- |
| Lớp, interface, enum | `UpperCamelCase`, thường là danh từ/vai trò | `TicketPricing`, `PaymentService` |
| Phương thức | `lowerCamelCase`, thường bắt đầu bằng động từ | `calculateTicketPriceVnd()`, `sendNotification()` |
| Biến, tham số | `lowerCamelCase`, đặt theo ý nghĩa và phạm vi | `customerAge`, `orderTotalVnd` |
| Hằng số `static final` | `UPPER_SNAKE_CASE` | `MINIMUM_ADULT_AGE`, `MAX_RETRY_COUNT` |
| Tên package | Chữ thường, phân cấp theo miền chức năng | `com.example.tickets` |
| Biến `boolean` | Tên đọc được như câu hỏi đúng/sai | `isChild`, `hasPermission`, `canRetry` |

Nguyên tắc chọn tên:

- **Nói lên mục đích:** `customerAge` rõ hơn `a`; `calculateTicketPriceVnd` rõ hơn `calc()`. Tránh `data`, `result`, `temp`, `value` khi có thể nêu chính xác chúng chứa gì.
- **Ghi đơn vị nếu dễ nhầm:** `timeoutMillis`, `priceVnd`, `fileSizeBytes`. Một tên `timeout` không nói được là mili giây hay giây.
- **Phân biệt khái niệm gần nhau:** `totalPriceVnd` và `discountAmountVnd` khác `discountPercent`; một số tiền khác một tỷ lệ.
- **Đúng phạm vi:** biến vòng lặp rất ngắn có thể là `i` nếu rõ ràng, nhưng tên có ý nghĩa cần dùng cho biến nghiệp vụ hoặc biến sống qua nhiều bước.
- **Nhất quán từ vựng:** chọn một cách gọi, chẳng hạn `customer`, rồi dùng xuyên suốt thay vì xen kẽ `client`, `buyer`, `user` cho cùng một khái niệm.
- **Không lạm dụng viết tắt:** `numberOfItems` dễ hiểu hơn `nItm`. Tránh ký tự dễ nhầm như `l` (chữ L thường), `I` (i hoa) hoặc `O` (o hoa) đứng riêng.
- **Tên hợp lệ vẫn có thể khó đọc:** Java cho phép nhiều ký tự Unicode trong identifier nhưng mã nguồn thường dễ cộng tác hơn với tên tiếng Anh, ký tự ASCII và quy ước nhất quán. Không dùng từ khóa Java làm tên biến.

Tên nên phản ánh hành vi thực tế. Chẳng hạn, một hàm kiểm tra rồi ghi dữ liệu không nên gọi `validate()` nếu nó còn tạo tác dụng phụ. Khi API được dùng ở nhiều nơi, đổi tên nên thực hiện bằng chức năng **Rename/Refactor** của IDE để cập nhật tất cả chỗ tham chiếu.

## 2. Thụt lề và dấu ngoặc nhọn giúp nhìn đúng luồng điều khiển

Một phong cách thông dụng cho Java:

1. Thụt **4 dấu cách cho mỗi cấp khối**; thiết lập formatter thống nhất trong dự án, không trộn tab và dấu cách.
2. Luôn dùng `{` và `}` cho thân `if`, `else`, vòng lặp, kể cả thân chỉ có một lệnh; đặt dấu mở khối sau điều kiện, dấu đóng khối thẳng hàng với cấu trúc điều khiển.
3. Dùng khoảng trắng quanh toán tử, sau dấu phẩy; cách nhóm các phương thức và biến nhất quán; tách các biểu thức quá dài ở vị trí hợp lý.
4. Căn lề theo **cấu trúc cú pháp**, không căn cho đẹp bằng số lượng dấu cách tùy ý. Chạy công cụ formatter trước khi đưa mã vào review.

Ví dụ sau **chỉ là đoạn mã trong một phương thức** và dễ gây lỗi:

```java
if (isMember)
    discountPercent = 10;
    System.out.println("Đã áp dụng giảm giá");
```

Dòng `println` **luôn chạy**, dù `isMember` là `false`: Java xác định thân `if` theo dấu ngoặc hoặc đúng một statement, không dựa vào thụt lề. Sửa bằng khối lệnh rõ ràng:

```java
if (isMember) {
    discountPercent = 10;
    System.out.println("Đã áp dụng giảm giá");
}
```

Thụt lề tốt giúp đọc luồng, nhưng dấu ngoặc nhọn mới xác định ranh giới khối. Tương tự, đặt `else` sát khối `if` tương ứng để tránh hiểu sai các nhánh lồng nhau. Không nên sửa lỗi điều khiển chỉ bằng formatter: phải rà soát cấu trúc chương trình.

## 3. Tránh “magic numbers” (số không giải thích)

**Magic number** là số được viết trực tiếp trong biểu thức khi người đọc không biết ý nghĩa hoặc lý do chọn nó:

```java
int age = 10;
int price = 200000;
if (age < 12) {
    price = price * 75 / 100;
}
```

Đọc riêng đoạn này không rõ `12` là mốc tuổi nào, `200000` có đơn vị gì, `75` biểu thị mức giá hay giảm giá. Những quy tắc này dễ bị sửa thiếu ở một trong nhiều chỗ.

Cách cải thiện phụ thuộc vào **bản chất** của giá trị:

| Trường hợp | Cách diễn đạt nên dùng |
| --- | --- |
| Ngưỡng, giới hạn, phí hay tỷ lệ nghiệp vụ cố định trong phiên bản mã | Hằng `private static final` với tên giải thích chính sách, ví dụ `MAX_RETRY_COUNT` |
| Khoảng thời gian | `Duration.ofSeconds(5)`, `Duration.ofMinutes(2)` thay vì số mili giây không rõ đơn vị |
| Giá trị cấu hình thay đổi theo môi trường hoặc vận hành | Đưa vào cấu hình có tên và kiểm tra hợp lệ, không cố định mã nguồn |
| Tập giá trị trạng thái có ý nghĩa | `enum` hay kiểu riêng thay cho số `0`, `1`, `2` khó hiểu |
| Số mang ý nghĩa toán học rõ ràng hoặc chỉ số cơ bản | `0`, `1` có thể giữ nguyên nếu ngữ cảnh thật sự hiển nhiên |

Không cần tạo hằng số cho *mọi* số. Chỉ đặt tên khi nó giúp nêu quy tắc, giải thích đơn vị, tránh trùng lặp hoặc gom một điểm thay đổi. Đặt tên `NUMBER_12` không cải thiện gì: **tên phải giải thích ý nghĩa, không lặp lại giá trị**. Hằng số `static final` chỉ bất biến theo tham chiếu/giá trị trường; đối tượng mutable mà nó trỏ tới vẫn có thể thay đổi.

## 4. Chương trình Java 17+ chạy độc lập

Lưu đúng tên tệp **`TicketPricing.java`** (không có khai báo `package`) với nội dung sau:

```java
public final class TicketPricing {
    private static final int MINIMUM_ADULT_AGE = 12;
    private static final int STANDARD_TICKET_PRICE_VND = 200_000;
    private static final int CHILD_DISCOUNT_PERCENT = 25;
    private static final int PERCENT_BASE = 100;

    private TicketPricing() {
    }

    public static void main(String[] args) {
        int youngerCustomerAge = 10;
        int adultCustomerAge = 12;

        System.out.println(
                "Khách " + youngerCustomerAge + " tuổi: "
                        + calculateTicketPriceVnd(youngerCustomerAge) + " VND");
        System.out.println(
                "Khách " + adultCustomerAge + " tuổi: "
                        + calculateTicketPriceVnd(adultCustomerAge) + " VND");
    }

    private static int calculateTicketPriceVnd(int customerAge) {
        if (customerAge < 0) {
            throw new IllegalArgumentException("Tuổi phải không âm");
        }

        boolean isChild = customerAge < MINIMUM_ADULT_AGE;
        if (isChild) {
            return STANDARD_TICKET_PRICE_VND
                    * (PERCENT_BASE - CHILD_DISCOUNT_PERCENT)
                    / PERCENT_BASE;
        }

        return STANDARD_TICKET_PRICE_VND;
    }
}
```

Chạy trong thư mục chứa tệp bằng JDK 17 trở lên (PowerShell, CMD, macOS hoặc Linux):

```bash
javac -encoding UTF-8 TicketPricing.java
java TicketPricing
```

**Kết quả chuẩn trên stdout:**

```text
Khách 10 tuổi: 150000 VND
Khách 12 tuổi: 200000 VND
```

Giải thích: `MINIMUM_ADULT_AGE` làm rõ chính sách **dưới 12 tuổi** được giảm 25%; khách đúng 12 tuổi trả giá chuẩn. `STANDARD_TICKET_PRICE_VND` giải thích đơn vị, `PERCENT_BASE` làm rõ phép tính phần trăm, còn `calculateTicketPriceVnd` nói rõ kết quả trả về. Dấu `_` trong literal số `200_000` chỉ giúp đọc mã; giá trị vẫn là số nguyên `200000`. Ví dụ dùng số nguyên VND và mức giảm chia hết, nên không phát sinh vấn đề làm tròn; nghiệp vụ tiền tệ có phần lẻ thường cần `BigDecimal` hoặc số đơn vị nhỏ nhất cùng quy tắc làm tròn rõ ràng.

## 5. Áp dụng khi sửa mã có sẵn

1. **Đọc ý nghĩa trước khi đổi tên:** xác định biến đại diện cho dữ liệu nào, đơn vị và phạm vi sống; chọn tên phù hợp hành vi thực tế.
2. **Đặt tên cho quy tắc:** thay ngưỡng và tỷ lệ khó hiểu bằng hằng số hoặc cấu hình có tên; tránh để cùng một chính sách có nhiều giá trị sao chép.
3. **Chuẩn hóa khối điều khiển:** thêm dấu ngoặc nếu cần, rà soát `if/else` và vòng lặp, rồi áp dụng formatter thống nhất.
4. **Kiểm tra hành vi sau khi sửa:** biên dịch và thử tại ngưỡng, ngay dưới/trên ngưỡng; với ví dụ trên là tuổi `11`, `12`, `13` và trường hợp tuổi âm. Việc thay tên hay format đơn thuần không được làm đổi logic.
5. **Giữ thay đổi dễ review:** thay đổi API công khai có thể ảnh hưởng mã gọi, reflection, tên JSON hoặc cấu hình ràng buộc bên ngoài; cần rà soát trước khi đổi tên.

**Tự kiểm tra:** Người đọc có hiểu mỗi tên khi tách khỏi đoạn code không? Các đơn vị có rõ không? Có số nào chứa chính sách cần giải thích không? Các nhánh có ngoặc và thụt lề phản ánh đúng điều kiện chạy không? Nếu hai người cùng sửa file, formatter có tạo ra khác biệt không cần thiết không? Đó là những dấu hiệu thực tế của mã Java dễ bảo trì.