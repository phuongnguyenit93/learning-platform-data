# Đánh đổi hiệu năng với độ rõ ràng và khả năng kiểm chứng

## 1. Mục tiêu bài học

Trong chương **Bối cảnh và đánh đổi** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta xem xét một tình huống thường gặp: làm thế nào để mã chạy đủ nhanh mà người khác vẫn hiểu được, kiểm thử được và thay đổi an toàn? Đây là một phần của mục tiêu chung: **hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không**.

Sau bài học, bạn có thể:

- Giải thích vì sao cải thiện thời gian chạy hoặc mức sử dụng bộ nhớ đôi khi làm tăng độ phức tạp của mã.
- Phân biệt vấn đề hiệu năng đã được đo với giả định rằng một cách viết “có vẻ nhanh hơn”.
- So sánh hai cách triển khai Java theo **hành vi, chi phí thời gian, bộ nhớ và khả năng kiểm chứng**.
- Đưa ra quyết định tối ưu hóa dựa trên yêu cầu thực tế, bằng chứng và mức độ rủi ro chấp nhận được.

## 2. Hiệu năng, độ rõ ràng và khả năng kiểm chứng là gì?

**Hiệu năng (performance)** phản ánh mức đáp ứng của hệ thống đối với các yêu cầu về tài nguyên và thời gian. Tùy bài toán, nhóm có thể quan tâm đến độ trễ của một yêu cầu, số yêu cầu xử lý trong một giây, thời gian hoàn tất tác vụ theo lô, mức dùng CPU, bộ nhớ hoặc áp lực thu gom rác (GC).

**Độ rõ ràng (clarity)** là khả năng người đọc hiểu đoạn mã đang thực hiện quy tắc nào, dữ liệu đi qua các bước ra sao, điều kiện nào tạo ra kết quả và những giả định nào đang được sử dụng. Tên tốt, luồng điều khiển dễ theo dõi và trách nhiệm được chia hợp lý thường giúp cải thiện độ rõ ràng.

**Khả năng kiểm chứng (verifiability)** là khả năng tạo được bằng chứng đáng tin rằng hành vi thỏa mãn yêu cầu: có thể viết kiểm thử xác định được kết quả, tái hiện trường hợp biên, kiểm tra các bất biến (invariant), đo hiệu năng trong điều kiện phù hợp và quan sát sự cố. Kiểm thử tự động là một công cụ quan trọng nhưng không phải nguồn bằng chứng duy nhất.

Ba thuộc tính này không luôn đối lập. Chọn thuật toán tốt hơn đôi khi **vừa nhanh hơn vừa dễ hiểu hơn**. Sự đánh đổi xuất hiện khi một tối ưu hóa đưa vào cấu trúc dữ liệu bổ sung, bộ nhớ đệm, trạng thái dùng chung, xử lý song song hoặc các nhánh đặc biệt. Những cơ chế đó có thể giảm thời gian chạy nhưng làm tăng số điều kiện cần hiểu và kiểm tra.

> **Nguyên tắc:** Chỉ chấp nhận độ phức tạp bổ sung khi lợi ích hiệu năng có liên quan đến yêu cầu của hệ thống và có bằng chứng đủ tin cậy. Mục tiêu là đáp ứng ràng buộc hiệu năng với mức phức tạp thấp nhất hợp lý, không phải tối đa hóa một chỉ số bằng mọi giá.

## 3. Ví dụ Java: tra cứu giá theo mã sản phẩm

Giả sử dịch vụ nhận danh sách quy tắc giá theo `sku` và cần tra giá trong quá trình xử lý đơn hàng. Để tập trung vào phép tra cứu, ta quy định:

- Mỗi quy tắc có `sku` không `null` và giá nguyên theo VND, không âm.
- Nếu có nhiều quy tắc trùng `sku`, **quy tắc xuất hiện đầu tiên trong danh sách** được ưu tiên.
- Nếu không tìm thấy `sku`, kết quả là `OptionalLong.empty()`.
- Danh sách dùng cho một lượt xử lý được xem như **ảnh chụp dữ liệu (snapshot)**; cập nhật giá cần tạo dữ liệu và chỉ mục mới.

Ví dụ sử dụng **Java 17** để tận dụng `record`.

### Cách A: duyệt danh sách, dễ theo dõi

```java
import java.util.List;
import java.util.Objects;
import java.util.OptionalLong;

public final class LinearPriceLookup {
    public record PriceRule(String sku, long priceVnd) {
        public PriceRule {
            Objects.requireNonNull(sku, "sku");
            if (priceVnd < 0) {
                throw new IllegalArgumentException("priceVnd must be >= 0");
            }
        }
    }

    public static OptionalLong findPrice(List<PriceRule> rules, String sku) {
        Objects.requireNonNull(rules, "rules");
        Objects.requireNonNull(sku, "sku");

        for (PriceRule rule : rules) {
            if (rule.sku().equals(sku)) {
                return OptionalLong.of(rule.priceVnd());
            }
        }
        return OptionalLong.empty();
    }
}
```

Ưu điểm của cách này là ý định rất trực tiếp: duyệt lần lượt, tìm phần tử đầu tiên khớp mã, trả giá tương ứng. Không cần trạng thái hay bước chuẩn bị. Trình tự duyệt cũng thể hiện rõ quy tắc ưu tiên phần tử đầu tiên.

Nhược điểm là trong trường hợp xấu nhất, mỗi lần tra cứu phải xem hết `n` phần tử, tức thời gian **O(n)**. Nếu cùng một danh sách lớn được tra hàng chục nghìn lần, công việc lặp có thể đáng kể.

### Cách B: tạo chỉ mục trước khi tra cứu nhiều lần

Thay vì duyệt danh sách ở mỗi lần tra cứu, ta có thể tạo một `Map` từ `sku` sang giá. Cách này thêm chi phí xây dựng chỉ mục và dùng bộ nhớ, đổi lại tra cứu trung bình nhanh hơn.

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.OptionalLong;

public final class IndexedPriceLookup {
    public record PriceRule(String sku, long priceVnd) {
        public PriceRule {
            Objects.requireNonNull(sku, "sku");
            if (priceVnd < 0) {
                throw new IllegalArgumentException("priceVnd must be >= 0");
            }
        }
    }

    public static Map<String, Long> buildIndex(List<PriceRule> rules) {
        Objects.requireNonNull(rules, "rules");
        Map<String, Long> result = new HashMap<>();
        for (PriceRule rule : rules) {
            // Giữ giá của phần tử xuất hiện đầu tiên khi SKU trùng.
            result.putIfAbsent(rule.sku(), rule.priceVnd());
        }
        return Map.copyOf(result); // Ảnh chụp chỉ đọc.
    }

    public static OptionalLong findPrice(Map<String, Long> index, String sku) {
        Objects.requireNonNull(index, "index");
        Objects.requireNonNull(sku, "sku");
        Long price = index.get(sku);
        return price == null ? OptionalLong.empty() : OptionalLong.of(price);
    }
}
```

Các trách nhiệm được tách rõ: `buildIndex` xây dựng chỉ mục, `findPrice` chỉ tra cứu. `putIfAbsent` giữ đúng quy tắc **SKU trùng thì lấy phần tử đầu tiên**; nếu dùng `put`, kết quả sẽ ngầm đổi thành lấy phần tử cuối cùng. `Map.copyOf` tạo một bản ánh xạ không thể sửa qua API trả về, giúp người gọi không vô tình thay đổi chỉ mục giữa chừng.

Lợi ích của cách B đi kèm những điều phải chú ý:

- Cần quyết định **khi nào tạo và thay thế chỉ mục**; chỉ mục cũ không tự cập nhật khi bảng giá thay đổi.
- Cần thêm bộ nhớ cho bảng băm và chi phí chuẩn bị trước khi tra cứu.
- Cần bảo đảm quy tắc trùng SKU và quy tắc dữ liệu đầu vào không bị đổi khi chuyển cách cài đặt.
- Cần kiểm tra rằng một lượt xử lý luôn tra cứu trên **cùng phiên bản dữ liệu**, nhất là khi có cập nhật đồng thời.

Đây là một đánh đổi thực tế: thuật toán hiệu quả hơn cho nhiều lần tra cứu, nhưng mô hình dữ liệu và vòng đời chỉ mục đòi hỏi thêm suy nghĩ, tài liệu và kiểm thử.

## 4. Đánh giá chi phí: không chỉ nhìn một lần tra cứu

Giả sử danh sách có `n` quy tắc và cần thực hiện `m` lần tra cứu. Với cách lập chỉ mục bằng bảng băm thông thường, có thể ước lượng:

| Tiêu chí | Duyệt danh sách (A) | Tạo chỉ mục (B) |
| --- | --- | --- |
| Chuẩn bị | Không cần chỉ mục: **O(1)** phụ trội | Duyệt và lập chỉ mục: **O(n)** trung bình |
| Một lần tra cứu | **O(n)** trong trường hợp xấu nhất | **O(1)** trung bình khi băm phân bố phù hợp |
| `m` lần tra cứu | Tối đa **O(m × n)** | **O(n + m)** trung bình, gồm cả xây dựng chỉ mục |
| Bộ nhớ phụ trội | **O(1)** cho thao tác tra cứu | **O(n)** cho chỉ mục |
| Khi dữ liệu thay đổi | Tra trên danh sách mới theo cách gọi hiện tại | Cần xây lại hoặc cập nhật chỉ mục đúng cách |
| Độ rõ ràng của quy tắc | Thể hiện trực tiếp thứ tự duyệt | Cần giải thích vòng đời và quy tắc xử lý SKU trùng |

Độ phức tạp ở trên là mô hình để so sánh, **không phải kết quả đo thời gian thực tế**. Thời gian còn phụ thuộc kích thước dữ liệu, vị trí phần tử được tìm, chi phí tính mã băm và so sánh chuỗi, tải bộ nhớ, JVM, GC và mẫu truy cập. Với một danh sách rất ngắn hoặc chỉ tra một lần, chi phí tạo `Map` có thể khiến cách B chậm hơn. Khi cùng một snapshot được tra nhiều lần, chi phí xây dựng chỉ mục có cơ hội được bù lại.

Như vậy, trước khi tối ưu hãy hỏi: một danh sách được tra **bao nhiêu lần**, dữ liệu **lớn đến đâu**, thay đổi **thường xuyên không**, mục tiêu **độ trễ hay thông lượng**, và **bộ nhớ còn bao nhiêu**?

## 5. Khả năng kiểm chứng phải đi cùng tối ưu hóa

Khi thay cách triển khai, đích đầu tiên là **giữ nguyên hành vi theo hợp đồng**. Với ví dụ trên, những bất biến cần bảo vệ gồm: giá không âm, ưu tiên SKU xuất hiện đầu tiên, không tìm thấy thì trả về rỗng, dữ liệu đầu vào không hợp lệ được xử lý theo quy định, và chỉ mục thể hiện đúng snapshot đã chọn.

Một số ca kiểm thử JUnit 5 có thể viết như sau. Vì hai lớp chứa hai `record` riêng, mỗi cách dùng danh sách cùng nội dung tương ứng với kiểu của nó:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.OptionalLong;
import org.junit.jupiter.api.Test;

class PriceLookupTest {
    @Test
    void preservesFirstMatchAndMissingSku() {
        var linearRules = List.of(
            new LinearPriceLookup.PriceRule("A", 12_000),
            new LinearPriceLookup.PriceRule("A", 14_000),
            new LinearPriceLookup.PriceRule("B", 0)
        );
        var indexedRules = List.of(
            new IndexedPriceLookup.PriceRule("A", 12_000),
            new IndexedPriceLookup.PriceRule("A", 14_000),
            new IndexedPriceLookup.PriceRule("B", 0)
        );

        var index = IndexedPriceLookup.buildIndex(indexedRules);

        assertEquals(OptionalLong.of(12_000),
            LinearPriceLookup.findPrice(linearRules, "A"));
        assertEquals(OptionalLong.of(12_000),
            IndexedPriceLookup.findPrice(index, "A"));
        assertEquals(OptionalLong.of(0),
            IndexedPriceLookup.findPrice(index, "B"));
        assertEquals(OptionalLong.empty(),
            IndexedPriceLookup.findPrice(index, "UNKNOWN"));
    }

    @Test
    void newDataRequiresNewIndex() {
        var oldRules = List.of(new IndexedPriceLookup.PriceRule("A", 12_000));
        var oldIndex = IndexedPriceLookup.buildIndex(oldRules);
        var newRules = List.of(new IndexedPriceLookup.PriceRule("A", 18_000));

        assertEquals(OptionalLong.of(12_000),
            IndexedPriceLookup.findPrice(oldIndex, "A"));
        assertEquals(OptionalLong.of(18_000),
            IndexedPriceLookup.findPrice(
                IndexedPriceLookup.buildIndex(newRules), "A"));
    }
}
```

Các kiểm thử này xác nhận **một số trường hợp quan trọng**, chứ chưa chứng minh hai cách luôn tương đương. Để tăng độ tin cậy, có thể tạo nhiều tập dữ liệu hợp lệ khác nhau và đối chiếu kết quả hai thuật toán với cùng `sku` (kiểm thử đối chiếu/differential testing), đặc biệt với danh sách rỗng, SKU trùng, giá bằng `0`, mã không tồn tại và danh sách lớn.

Với hệ thống có nhiều luồng hoặc thay đổi dữ liệu theo thời gian, còn phải kiểm tra hành vi khi **snapshot được thay thế**. Chẳng hạn, cách thiết kế giữ `Map` bất biến theo phiên bản và chuyển cả tham chiếu sang bản mới sẽ dễ lý giải hơn so với việc nhiều luồng cùng sửa một `HashMap` dùng chung. Bất biến của `Map` không tự bảo đảm toàn bộ cơ chế xuất bản và chuyển phiên bản đều đúng; cần thiết kế và kiểm chứng cả vòng đời cập nhật.

## 6. Đo hiệu năng sao cho đáng tin

Chỉ nhìn vào mã hoặc đo một lần bằng `System.nanoTime()` thường không đủ để kết luận một phương án nhanh hơn. JVM có cơ chế biên dịch JIT, tối ưu tại thời gian chạy và GC; số đo còn chịu ảnh hưởng của môi trường, đầu vào và cách xây phép thử.

Một quy trình phù hợp gồm:

1. **Đặt mục tiêu có đơn vị:** ví dụ p95 độ trễ tra cứu cần đáp ứng một giới hạn đã xác định, hoặc toàn bộ đợt xử lý phải hoàn tất trong ngân sách thời gian và bộ nhớ. Chọn ngưỡng từ yêu cầu thực tế, không tự đặt sau khi nhìn số đo.
2. **Tìm điểm nghẽn trước:** thu thập số liệu từ profiler, metrics hoặc tracing ở môi trường đại diện để biết chi phí nằm ở truy vấn dữ liệu, tính toán, cấp phát bộ nhớ hay I/O. Tối ưu sai vị trí thường không cải thiện trải nghiệm.
3. **Thiết kế phép đo đại diện:** sử dụng kích thước danh sách, số lần tra, tỷ lệ tìm thấy/không tìm thấy và tần suất cập nhật tương tự môi trường mục tiêu. Đo cả lúc xây chỉ mục nếu ứng dụng thực sự phải trả chi phí đó.
4. **So sánh trong điều kiện tương đương:** sử dụng cùng JDK, cấu hình JVM, phần cứng và dữ liệu; chạy nhiều lượt. Với microbenchmark Java, có thể dùng **JMH** để kiểm soát warm-up, fork và cách sử dụng kết quả, tránh nhiều sai lệch thường gặp.
5. **Kiểm tra tác động toàn hệ thống:** theo dõi thông lượng, các phân vị độ trễ (p95/p99 khi thích hợp), bộ nhớ, cấp phát và GC. Một tối ưu hóa nhỏ ở hàm có thể không cải thiện độ trễ đầu cuối, thậm chí làm tăng áp lực bộ nhớ.
6. **Kiểm chứng hành vi sau thay đổi:** chạy kiểm thử hồi quy, kiểm tra các bất biến và so sánh kết quả trước khi chấp nhận phương án mới.

Ví dụ, nếu một đợt xử lý có 100.000 quy tắc nhưng chỉ tra đúng **một** SKU, việc tạo chỉ mục cho cả danh sách có thể không hợp lý. Nếu cùng dữ liệu được tra **rất nhiều lần**, cách lập chỉ mục đáng thử nghiệm. Hai tình huống chỉ giúp xác định **giả thuyết**; kết luận cuối cùng cần dựa trên số đo.

### Phân biệt ba loại bằng chứng

| Bằng chứng | Câu hỏi trả lời | Điều không thể kết luận chỉ từ đó |
| --- | --- | --- |
| Kiểm thử chức năng | Kết quả có đúng theo các trường hợp được kiểm tra không? | Phương án có đạt mục tiêu hiệu năng không? |
| Benchmark/profiling | Chi phí thực thi ở điều kiện đo cụ thể ra sao? | Mọi trường hợp nghiệp vụ đều đúng không? |
| Metrics vận hành | Hệ thống thật có đáp ứng mục tiêu dưới tải thực tế không? | Một nhánh thuật toán có đúng với mọi đầu vào không? |

Một thay đổi hiệu năng đáng tin cần được nhìn từ **cả tính đúng đắn lẫn số liệu đo được**, phù hợp với mục tiêu của dịch vụ.

## 7. Những kiểu tối ưu hóa dễ phát sinh đánh đổi

Không phải mọi kỹ thuật tăng tốc đều có cùng chi phí duy trì:

| Kỹ thuật | Lợi ích có thể đạt | Rủi ro đối với độ rõ ràng và kiểm chứng | Cách giảm rủi ro |
| --- | --- | --- | --- |
| Dùng chỉ mục/bảng băm | Giảm chi phí tra cứu lặp | Thêm bộ nhớ, bước xây chỉ mục, quy tắc trùng khóa | Tách hàm xây và tra; xác định vòng đời snapshot; kiểm thử trùng khóa |
| Cache kết quả | Tránh tính toán hoặc I/O lặp | Dữ liệu cũ, vô hiệu hóa cache, khó tái hiện lỗi theo thời gian | Xác định thời hạn/điều kiện vô hiệu hóa, quan sát hit/miss, kiểm thử dữ liệu hết hạn |
| Xử lý song song | Tăng thông lượng nếu tác vụ đủ độc lập | Race condition, thứ tự kết quả khó dự đoán, kiểm thử không ổn định | Hạn chế trạng thái dùng chung; quy định tính độc lập và thứ tự; kiểm thử đồng thời |
| Gom lô/batch | Giảm chi phí từng thao tác I/O | Tăng độ trễ chờ, lỗi một phần và cơ chế retry phức tạp | Quy định kích thước lô, tính idempotent, xử lý lỗi từng mục |
| Tối ưu vi mô (micro-optimization) | Giảm một lượng chi phí nhỏ trong đoạn rất nóng | Biểu thức khó đọc, phụ thuộc chi tiết JVM, lợi ích dễ mất sau nâng cấp | Chỉ dùng khi profiler chỉ rõ điểm nóng; benchmark và ghi rõ lý do |

Điều đáng cân nhắc không chỉ là *“Có nhanh hơn không?”* mà còn là *“Khi phát hiện sai lệch hoặc yêu cầu thay đổi, nhóm có thể tìm nguyên nhân và sửa an toàn không?”*. Một bộ nhớ đệm có tỷ lệ hit cao nhưng trả dữ liệu lỗi thời ở bước thanh toán có thể gây hậu quả nghiêm trọng hơn việc chậm thêm một chút.

## 8. Cách ra quyết định trong dự án

Có thể dùng các câu hỏi dưới đây trong code review hoặc cuộc thảo luận thiết kế:

1. **Yêu cầu hiệu năng cụ thể là gì?** Cần thời gian phản hồi, thông lượng hay giới hạn bộ nhớ nào; mức vi phạm hiện tại ra sao?
2. **Điểm nghẽn đã được xác định chưa?** Phần mã dự định tối ưu có thực sự ảnh hưởng đáng kể đến chỉ số đầu cuối không?
3. **Phương án đơn giản nhất đáp ứng yêu cầu là gì?** Có thể giảm số lần gọi, tránh công việc thừa hoặc thay cấu trúc dữ liệu trước khi thêm trạng thái phức tạp không?
4. **Hành vi nào cần được giữ nguyên?** Đặc biệt là thứ tự, trường hợp rỗng, dữ liệu trùng, lỗi đầu vào và ngữ nghĩa cập nhật.
5. **Chi phí mới là gì?** Bộ nhớ, khởi tạo, độ trễ khi cập nhật, khó quan sát, khó kiểm thử và công bảo trì.
6. **Có thể cô lập tối ưu hóa không?** Một API rõ ràng và các hàm thuần sẽ giúp kiểm thử và thay thế phương án dễ hơn.
7. **Bằng chứng có đủ chưa?** Có kiểm thử hồi quy, benchmark đại diện và số liệu vận hành để xác nhận hiệu quả không?

### Ba lựa chọn hợp lý trong ba bối cảnh

| Bối cảnh | Quyết định nên cân nhắc | Lý do |
| --- | --- | --- |
| Danh sách nhỏ, tra một vài lần, chưa có vấn đề độ trễ | Giữ duyệt tuần tự | Cách đọc đơn giản, tránh chi phí xây dựng và duy trì chỉ mục. |
| Danh sách lớn, tra rất nhiều lần trên cùng snapshot | Thử dùng chỉ mục bất biến, đo toàn bộ chi phí | Có khả năng giảm thời gian lặp lại, trong khi snapshot giúp dễ kiểm chứng hơn. |
| Dữ liệu cập nhật liên tục và yêu cầu luôn thấy giá mới nhất | Làm rõ mô hình nhất quán trước khi cache hoặc lập chỉ mục | Có thể phải ưu tiên tính đúng đắn và cơ chế cập nhật hơn tốc độ tra cứu đơn lẻ. |

Quyết định có thể thay đổi khi quy mô, tải hoặc yêu cầu đổi khác. Ghi lại **lý do lựa chọn**, điều kiện áp dụng và kết quả đo quan trọng giúp người đến sau biết khi nào cần đánh giá lại.

## 9. Tự kiểm tra

1. Vì sao `Map` tra cứu trung bình O(1) không có nghĩa toàn bộ bài toán dùng `Map` luôn nhanh hơn duyệt danh sách?
2. Nếu thay `putIfAbsent` thành `put` trong ví dụ, hành vi nào sẽ thay đổi khi có SKU trùng? Tại sao đây là lỗi về tính đúng đắn, dù kết quả benchmark có thể tốt?
3. Một cache làm giảm p95 độ trễ nhưng đôi lúc trả giá cũ. Bạn cần biết thêm điều gì trước khi chấp nhận?
4. Độ bao phủ kiểm thử 100% có đủ chứng minh tối ưu hóa giữ nguyên hành vi và đạt mục tiêu hiệu năng không?

**Gợi ý:** (1) Phải tính cả chi phí tạo chỉ mục, bộ nhớ, số lần tra và cập nhật dữ liệu. (2) `put` ghi đè giá trước, làm quy tắc ưu tiên phần tử đầu tiên thành phần tử cuối; nhanh không bù được sai đặc tả. (3) Yêu cầu nhất quán dữ liệu, tác động sai giá, cơ chế vô hiệu hóa và kết quả đo trong tải thực. (4) Không; cần ca kiểm thử đúng rủi ro, đối chiếu hành vi và phép đo hiệu năng đại diện.

## 10. Ghi nhớ

**Hiệu năng là một thuộc tính chất lượng, nhưng không đứng riêng khỏi tính đúng đắn, độ rõ ràng và khả năng kiểm chứng.** Hãy ưu tiên giải pháp rõ ràng đáp ứng yêu cầu; khi có điểm nghẽn đã đo được, chọn tối ưu hóa có lợi ích đáng kể, giữ hợp đồng hành vi và cô lập phần phức tạp để dễ kiểm thử. Một hệ thống chỉ thật sự dễ phát triển lâu dài khi nhóm vừa có thể **tin vào kết quả**, vừa có thể **hiểu và thay đổi mã** một cách an toàn.
