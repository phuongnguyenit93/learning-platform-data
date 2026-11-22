# Khả năng đọc và giải thích ý định

> **Chương:** Các chiều chất lượng  
> **Học phần:** CODE_QUALITY_FUNDAMENTALS — Hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

Mã nguồn không chỉ được viết để máy tính thực thi. Trong suốt vòng đời sản phẩm, lập trình viên phải đọc mã để sửa lỗi, bổ sung tính năng, đánh giá tác động của thay đổi và kiểm tra tính đúng đắn. Vì vậy, **khả năng đọc** (*readability*) và **khả năng giải thích ý định** (*intention revealing*) là hai thuộc tính quan trọng của chất lượng mã.

Một đoạn mã tốt giúp người đọc trả lời được cả hai câu hỏi:

1. **Mã đang làm gì?** Có thể theo dõi dữ liệu và luồng xử lý mà không mất quá nhiều công sức không?
2. **Vì sao mã phải làm như vậy?** Có thể nhận ra quy tắc nghiệp vụ, điều kiện áp dụng và mục đích của quyết định thiết kế không?

## 1. Phân biệt khả năng đọc và khả năng giải thích ý định

Hai thuộc tính liên quan chặt chẽ nhưng không đồng nhất:

| Thuộc tính | Người đọc cần hiểu | Dấu hiệu tốt | Ví dụ về vấn đề |
| --- | --- | --- | --- |
| **Khả năng đọc** | Cấu trúc, thứ tự xử lý, giá trị và điều kiện | Tên nhất quán, khối mã nhỏ có trách nhiệm rõ, ít lồng nhau không cần thiết | Một biểu thức dài kết hợp nhiều phép phủ định, tên biến là các chữ cái đơn lẻ |
| **Khả năng giải thích ý định** | Mục tiêu và quy tắc đứng sau thao tác | Tên phản ánh ngôn ngữ nghiệp vụ, hằng số có nghĩa, ranh giới trách nhiệm rõ | Điều kiện so sánh với số `500000` nhưng không biết đó là ngưỡng gì |

Ví dụ:

```java
if (total >= 500000) {
    fee = 0;
}
```

Cú pháp trên rất dễ đọc, nhưng chưa thể biết `total` là tổng tiền trước hay sau giảm giá, `500000` là ngưỡng gì và `fee` là loại phí nào. Đổi tên để biểu đạt ý định:

```java
if (subtotalAfterDiscountVnd >= FREE_SHIPPING_MIN_SUBTOTAL_VND) {
    shippingFeeVnd = 0;
}
```

Người đọc nay có thể suy ra đây là điều kiện miễn phí vận chuyển dựa trên tổng tiền hàng sau giảm giá. Tuy nhiên, **tên tốt không thay thế đặc tả nghiệp vụ**: nếu quy tắc thực tế còn phụ thuộc khu vực giao hàng hoặc trạng thái đơn, mã vẫn phải thể hiện các điều kiện đó.

> **Nguyên tắc:** Mã dễ đọc giúp người khác *theo dõi cách thực hiện*; mã thể hiện ý định giúp họ *hiểu mục đích và giới hạn của cách thực hiện*.

## 2. Vì sao hai thuộc tính này ảnh hưởng đến chất lượng sản phẩm?

Giả sử một yêu cầu mới buộc hệ thống thay đổi ngưỡng miễn phí vận chuyển. Nếu không xác định được các biến và điều kiện liên quan, lập trình viên có thể thay nhầm một giá trị dùng cho chính sách khác. Mã khó hiểu làm tăng thời gian điều tra, số giả định cần kiểm chứng và rủi ro sửa sai hành vi.

Khả năng đọc và ý định rõ ràng thường mang lại những lợi ích sau:

- **Đánh giá thay đổi chính xác hơn:** người sửa nhận diện được điều kiện nào thuộc chính sách, điều kiện nào bảo vệ tính hợp lệ của dữ liệu.
- **Review hiệu quả hơn:** người kiểm tra có thể so sánh mã với yêu cầu nghiệp vụ thay vì chỉ đoán mục đích từ cú pháp.
- **Phát hiện lỗi sớm hơn:** tên gọi và cấu trúc rõ giúp các điều kiện bị thiếu hoặc mâu thuẫn dễ lộ diện.
- **Bảo trì dễ hơn:** lập trình viên mới có thể dựng lại mô hình xử lý trong đầu mà không phải lần theo quá nhiều hàm hoặc trạng thái ẩn.
- **Kiểm thử có ý nghĩa hơn:** tên và ranh giới của quy tắc gợi ra các trường hợp biên cần kiểm tra.

Đây không phải lời bảo đảm rằng mã dễ đọc sẽ luôn đúng hoặc an toàn. **Tính đúng đắn vẫn cần được xác nhận** bằng yêu cầu, thử nghiệm, review và quan sát hành vi thực tế.

## 3. Những dấu hiệu làm người đọc khó hiểu mã

| Dấu hiệu | Tác hại đối với người đọc | Hướng cải thiện |
| --- | --- | --- |
| Tên mơ hồ như `x`, `data`, `process()` | Không biết dữ liệu hoặc thao tác đại diện cho khái niệm gì | Đặt tên theo vai trò và đơn vị, chẳng hạn `subtotalAfterDiscountVnd` |
| Số hoặc chuỗi không có ngữ cảnh (*magic number/string*) | Không rõ giá trị là ngưỡng, trạng thái hay mã tích hợp | Dùng hằng số có tên hoặc kiểu miền nghiệp vụ thích hợp |
| Điều kiện nhiều tầng và nhiều phủ định | Phải giữ nhiều nhánh logic trong trí nhớ khi đọc | Đơn giản hóa biểu thức, tách điều kiện có ý nghĩa, cân nhắc *guard clause* |
| Hàm làm nhiều việc | Khó phát biểu trách nhiệm chính của hàm | Tách theo trách nhiệm khi có ranh giới rõ ràng |
| Hàm phụ có tên quá chung chung | Phải nhảy sang nhiều nơi mới hiểu ý nghĩa | Đặt tên chỉ rõ mục đích và giữ luồng chính dễ theo dõi |
| Tác dụng phụ bị che giấu | Tên gợi ý truy vấn nhưng hàm lại cập nhật trạng thái hoặc gửi thông báo | Đặt tên phản ánh tác động và làm rõ giao diện |
| Bình luận mô tả lại câu lệnh hoặc đã lỗi thời | Tăng nhiễu, thậm chí khiến người đọc tin sai | Để mã thể hiện *làm gì*; dùng bình luận cho lý do không thể suy ra từ mã |
| Nhiều tên gọi cho cùng một khái niệm | Khó biết các biến/hàm có cùng ý nghĩa hay không | Thống nhất từ vựng miền nghiệp vụ trong cùng phạm vi |

Không nên áp dụng máy móc các quy tắc như “hàm càng ngắn càng tốt”, “mỗi điều kiện đều cần một hàm riêng” hoặc “không bao giờ được viết bình luận”. Mục đích cuối cùng là **giảm công sức cần thiết để hiểu đúng hành vi**.

## 4. Ví dụ Java: biểu đạt rõ một chính sách miễn phí vận chuyển

Giả sử hệ thống có quy tắc:

- Phí giao hàng thông thường là **30.000 đồng**.
- Đơn hàng **chưa hủy**, có **tổng tiền hàng sau giảm giá từ 500.000 đồng trở lên** và thuộc **vùng giao hàng được hỗ trợ (mã vùng 1)** thì được miễn phí giao hàng.
- Các đơn hàng còn lại chịu mức phí thông thường.

Trong ví dụ này, mọi số tiền đều được biểu diễn bằng số nguyên đơn vị đồng Việt Nam (`long`). Đây là một chính sách giả định để minh họa cách diễn đạt ý định.

### 4.1. Cách viết khó hiểu hơn

```java
public static long fee(long total, int zone, boolean cancelled) {
    long f = 30000;
    if (total >= 500000 && zone == 1 && !cancelled) {
        f = 0;
    }
    return f;
}
```

Đoạn mã hoạt động theo quy tắc đã nêu, nhưng người đọc cần dựa vào kiến thức bên ngoài để biết:

- `total` đã trừ giảm giá hay chưa;
- `zone == 1` có ý nghĩa nghiệp vụ gì;
- `500000` và `30000` là hai loại giá trị nào;
- điều kiện tổng hợp biểu thị chính sách nào.

### 4.2. Cách viết thể hiện ý định

```java
public final class ShippingFeePolicy {
    private static final long STANDARD_SHIPPING_FEE_VND = 30_000L;
    private static final long FREE_SHIPPING_MIN_SUBTOTAL_VND = 500_000L;
    private static final int SUPPORTED_DELIVERY_ZONE_CODE = 1;

    private ShippingFeePolicy() {
        // Lớp chứa chính sách, không cần tạo đối tượng.
    }

    public static long calculateShippingFeeVnd(
            long subtotalAfterDiscountVnd,
            int deliveryZoneCode,
            boolean cancelled) {

        boolean isActiveOrder = !cancelled;
        boolean reachesFreeShippingThreshold =
                subtotalAfterDiscountVnd >= FREE_SHIPPING_MIN_SUBTOTAL_VND;
        boolean hasSupportedDeliveryZone =
                deliveryZoneCode == SUPPORTED_DELIVERY_ZONE_CODE;

        boolean eligibleForFreeShipping =
                isActiveOrder
                && reachesFreeShippingThreshold
                && hasSupportedDeliveryZone;

        return eligibleForFreeShipping ? 0L : STANDARD_SHIPPING_FEE_VND;
    }
}
```

**Điểm cải thiện:**

1. Tên hàm `calculateShippingFeeVnd` nói rõ kết quả là phí vận chuyển tính bằng đồng.
2. Tên tham số `subtotalAfterDiscountVnd` chốt ý nghĩa của con số đầu vào.
3. Hằng số giúp phân biệt **mức phí**, **ngưỡng áp dụng** và **mã vùng**, tránh các con số không có ngữ cảnh.
4. Các biến Boolean diễn đạt ba điều kiện độc lập của quy tắc.
5. Biến `eligibleForFreeShipping` tổng hợp ý định nghiệp vụ, khiến câu lệnh trả về dễ đọc.

Khi áp dụng trong dự án thật, nếu mã vùng giao hàng có nhiều giá trị hoặc quy tắc phức tạp, có thể cân nhắc một kiểu dữ liệu miền nghiệp vụ thay cho `int`. Việc thiết kế kiểu dữ liệu nên dựa trên nhu cầu thực tế, tránh tăng số lớp chỉ để che một phép so sánh đơn giản.

### 4.3. Kiểm tra hành vi trước và sau refactor

Refactor phải giữ nguyên hành vi đã xác định. Với đầu vào tương ứng, hai cách viết trên phải cho cùng kết quả:

| Tổng tiền sau giảm giá | Mã vùng | Đã hủy? | Phí vận chuyển mong đợi |
| ---: | ---: | :---: | ---: |
| 499.999 đ | 1 | Không | 30.000 đ |
| 500.000 đ | 1 | Không | 0 đ |
| 600.000 đ | 2 | Không | 30.000 đ |
| 600.000 đ | 1 | Có | 30.000 đ |
| 600.000 đ | 1 | Không | 0 đ |

Đặc biệt, **500.000 đồng** là trường hợp biên quan trọng: đổi `>=` thành `>` sẽ làm sai chính sách dù mã vẫn biên dịch. Tên rõ giúp đánh giá ý định; kiểm thử giúp xác nhận hành vi.

## 5. Làm rõ luồng xử lý bằng điều kiện bảo vệ

Nhiều tầng `if` khiến người đọc phải giữ trong đầu một chuỗi điều kiện để tìm ra thao tác chính. Ví dụ:

```java
void createInvoice(Order order) {
    if (order != null) {
        if (order.isConfirmed()) {
            if (!order.isCancelled()) {
                invoiceRepository.create(order);
            }
        }
    }
}
```

Trong một hàm chỉ có nhiệm vụ trên, có thể dùng *guard clause* để đưa các trường hợp không hợp lệ ra đầu hàm:

```java
void createInvoice(Order order) {
    if (order == null) {
        return;
    }
    if (!order.isConfirmed()) {
        return;
    }
    if (order.isCancelled()) {
        return;
    }

    invoiceRepository.create(order);
}
```

Người đọc dễ nhìn thấy “chỉ tạo hóa đơn cho đơn đã xác nhận và chưa hủy”. Hai đoạn tương đương về việc **có gọi** `invoiceRepository.create(order)` hay không. Trong hệ thống thật, cần xác định liệu đầu vào không hợp lệ phải được bỏ qua, trả kết quả lỗi hay ném ngoại lệ; đó là một quyết định nghiệp vụ, không thể suy từ kỹ thuật refactor.

Guard clause hữu ích khi làm phẳng luồng xử lý. Tuy nhiên, nhiều lệnh `return` rải rác trong một hàm lớn cũng có thể gây khó theo dõi; hãy chọn cấu trúc rõ nhất với tình huống cụ thể.

## 6. Đặt tên để làm lộ ý định

Tên tốt phải cho người đọc đủ thông tin để hiểu vai trò, không nhất thiết càng dài càng tốt.

**Tên phản ánh nghiệp vụ:**

```java
// Mơ hồ: amount là khoản tiền nào?
long amount = order.getTotal();

// Rõ hơn nếu thực sự là số tiền phải thanh toán:
long payableAmountVnd = order.getTotalPayableVnd();
```

Không nên đổi tên thành `payableAmountVnd` nếu giá trị thực tế lại là tổng tiền *trước* khuyến mại. **Tên phải đúng với ngữ nghĩa**, không chỉ nghe có vẻ chuyên nghiệp.

**Tên Boolean diễn đạt một mệnh đề:**

```java
boolean valid = user != null && user.isActive();
boolean isActiveUser = user != null && user.isActive();
```

Tên thứ hai giúp người đọc hiểu `true` có nghĩa gì. Khi có thể, tránh phủ định kép như `!isNotApproved`; với điều kiện phức tạp, chọn tên thể hiện một quy tắc có thể phát biểu thành câu.

**Giữ từ vựng nhất quán:** nếu cả nhóm gọi số tiền sau giảm giá là “tổng tiền phải trả”, không nên dùng lẫn `subtotal`, `netTotal`, `payableAmount` khi chúng thực chất cùng một khái niệm. Ngược lại, nếu ba giá trị khác nhau, phải phân biệt rõ. Sự nhất quán giúp các tên trở thành một bản đồ miền nghiệp vụ.

## 7. Khi nào cần bình luận, khi nào cần sửa mã?

Bình luận thường không nên lặp lại điều có thể thấy trực tiếp:

```java
// Tăng bộ đếm lên một.
retryCount++;
```

Bình luận có ích khi ghi lại **lý do** mà tên và cấu trúc không thể biểu đạt đủ, chẳng hạn một ràng buộc từ hệ thống tích hợp:

```java
// Ví dụ giả định: đối tác vận chuyển cũ quy định mã vùng 1 là vùng hỗ trợ.
// Khi thay đổi mã này, cần đồng bộ với cấu hình của đối tác.
private static final int SUPPORTED_DELIVERY_ZONE_CODE = 1;
```

Đây là **ngữ cảnh giả định của ví dụ**, không phải một yêu cầu có thật của mọi hệ thống. Trong dự án thực tế, chỉ ghi bình luận kiểu này khi có căn cứ từ đặc tả hoặc quyết định kỹ thuật. Nếu tên hàm sai hoặc điều kiện khó đọc, hãy sửa mã trước khi thêm nhiều bình luận giải thích cú pháp.

## 8. Quy trình cải thiện mà không làm sai hành vi

Khi gặp mã khó đọc, có thể thực hiện theo trình tự:

1. **Xác định hành vi hiện tại:** đầu vào, đầu ra, tác dụng phụ, các trường hợp biên và quy tắc nghiệp vụ cần giữ.
2. **Nêu ý định bằng lời:** viết một hoặc hai câu giải thích điều kiện để tính toán hay ra quyết định.
3. **Đổi tên đúng nghĩa:** biến, tham số, hàm và hằng số; thêm đơn vị cho giá trị dễ gây nhầm lẫn.
4. **Giảm tải nhận thức:** tách điều kiện mang ý nghĩa riêng, làm phẳng phần lồng nhau, đặt thao tác chính ở vị trí dễ thấy.
5. **Đối chiếu hành vi:** dùng kiểm thử hiện có hoặc bổ sung các trường hợp đại diện và biên; kiểm tra đặc biệt với `null`, điều kiện phủ định và so sánh `>` / `>=`.
6. **Review từ góc nhìn người mới:** liệu có thể hiểu *điều kiện để làm gì* mà không cần tác giả giải thích trực tiếp?

Việc đổi tên hoặc trích hàm có thể yêu cầu cập nhật các nơi gọi, đặc biệt với API công khai. Trước khi refactor cần xác định phạm vi ảnh hưởng. Những cải thiện chỉ mang tính trình bày không được tự ý thay đổi xử lý lỗi, thứ tự tác dụng phụ hoặc quy tắc tính toán.

## 9. Các đánh đổi và ngộ nhận thường gặp

- **Ít dòng hơn không đồng nghĩa dễ hiểu hơn.** Một biểu thức ngắn nhưng dày đặc điều kiện đôi khi khó đọc hơn ba biến Boolean có tên rõ.
- **Nhiều hàm nhỏ không tự động tốt hơn.** Nếu phải mở năm hàm chỉ để hiểu một quyết định đơn giản, mức độ phân tán có thể làm tăng công sức đọc.
- **Tên dài không bảo đảm chính xác.** `calculateFinalPriceAfterAllPromotionsIncludingTax()` vẫn gây hiểu lầm nếu xử lý thực tế chưa tính thuế.
- **Bình luận không thay thế kiểm thử.** Bình luận có thể lỗi thời; kiểm thử các trường hợp quan trọng giúp đối chiếu hành vi.
- **Dễ đọc phụ thuộc vào người đọc và ngữ cảnh.** Một thuật ngữ chuyên ngành có thể ngắn, chính xác với nhóm nhưng cần giải thích ở ranh giới nơi người mới hoặc nhóm khác sử dụng.
- **Khả năng đọc chỉ là một chiều chất lượng.** Cần đánh giá đồng thời tính đúng đắn, hiệu năng, bảo mật, khả năng kiểm thử và khả năng thay đổi theo yêu cầu thực tế.

## 10. Tự đánh giá một đoạn mã

Hãy thử trả lời những câu hỏi sau khi đọc một hàm mà bạn chưa từng thấy:

| Câu hỏi | Dấu hiệu cần xem lại |
| --- | --- |
| Có thể nói mục đích của hàm trong một câu không? | Hàm không có trách nhiệm chính rõ ràng |
| Mỗi tên quan trọng có thể liên hệ với dữ liệu hoặc khái niệm nghiệp vụ không? | Tên chung chung, đơn vị bị ẩn |
| Các con số và trạng thái có ý nghĩa rõ không? | Nhiều giá trị “bí ẩn” trong điều kiện |
| Có dễ nhận ra đường đi chính và các trường hợp ngoại lệ không? | Lồng nhau sâu, phủ định liên tiếp |
| Có thể xác định điều kiện biên để kiểm thử không? | Quy tắc ẩn trong một biểu thức khó giải thích |
| Nếu đổi một quy tắc, có biết phần mã nào phải thay không? | Trách nhiệm pha trộn hoặc điều kiện nằm rải rác |

### Bài tập ngắn

Cho đoạn mã:

```java
if (customer != null && customer.getPoints() >= 1000 && !customer.isBlocked()) {
    level = 2;
}
```

Hãy tự thực hiện ba việc:

1. Phát biểu bằng một câu điều kiện để khách hàng đạt `level = 2`. Chỗ nào còn chưa thể kết luận chỉ từ mã?
2. Đề xuất tên cho ngưỡng `1000` và giá trị `2` dựa trên *một đặc tả giả định được nêu rõ*, chẳng hạn “đạt ít nhất 1.000 điểm và không bị khóa thì trở thành thành viên hạng Bạc”.
3. Viết lại bằng các điều kiện có tên, rồi kiểm tra ba trường hợp: **999 điểm**, **1.000 điểm**, **1.000 điểm nhưng bị khóa**. Tránh thay đổi cách xử lý `customer == null` khi refactor.

Từ một câu lệnh ngắn, bạn có thể thấy sự khác biệt giữa **đọc được phép so sánh** và **giải thích được chính sách mà phép so sánh thực thi**.

## Ghi nhớ

Khả năng đọc giúp mã dễ theo dõi; khả năng giải thích ý định giúp người khác hiểu *tại sao* luồng xử lý tồn tại. Hãy ưu tiên tên đúng nghĩa, quy tắc thể hiện trực tiếp, cấu trúc phù hợp và kiểm thử bảo vệ hành vi. Mục tiêu của refactor là để người tiếp theo hiểu và sửa mã chính xác với ít giả định hơn.
