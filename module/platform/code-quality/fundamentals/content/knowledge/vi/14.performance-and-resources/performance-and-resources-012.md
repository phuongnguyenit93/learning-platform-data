# Ghi lại giả thiết khiến một tối ưu có lợi

Một thay đổi giúp chương trình chạy nhanh hơn trong một phép thử chưa chắc làm hệ thống tốt hơn khi vận hành. Xây chỉ mục để tìm kiếm có thể hiệu quả nếu dữ liệu lớn và được truy vấn nhiều lần, nhưng lãng phí nếu chỉ tìm một lần. Thêm cache có thể giảm độ trễ ở luồng đọc lặp lại, nhưng gây dữ liệu cũ hoặc tiêu tốn bộ nhớ nếu tỷ lệ trúng thấp. Chạy nhiều tác vụ song song có thể tăng thông lượng, nhưng lại làm nghẽn cơ sở dữ liệu nếu tài nguyên phía sau đã bão hòa.

Bài học thuộc chương **Hiệu năng và tài nguyên** của **CODE_QUALITY_FUNDAMENTALS**. Mục tiêu của module là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Trọng tâm của bài này là **ghi rõ những giả thiết khiến một phương án tối ưu thực sự có lợi**, cách kiểm chứng chúng bằng số liệu và khi nào phải xem xét lại quyết định.

## 1. Một tối ưu chỉ có lợi trong những điều kiện nhất định

Một quyết định tối ưu thường dựa trên một hoặc nhiều điều kiện:

- Kích thước dữ liệu đủ lớn để khác biệt thuật toán có ý nghĩa.
- Tác vụ được lặp lại đủ nhiều để bù chi phí chuẩn bị.
- Dữ liệu ít thay đổi nên có thể tái sử dụng kết quả hoặc cấu trúc đã tính.
- Thành phần cần tối ưu thực sự là nút thắt của luồng nghiệp vụ.
- Việc dùng thêm bộ nhớ vẫn nằm trong giới hạn tài nguyên.
- Phản hồi nhanh hơn không vi phạm tính đúng đắn, độ tươi, bảo mật hoặc hợp đồng nghiệp vụ.
- Lợi ích đo được trong môi trường đại diện lớn hơn nhiễu của phép đo và chi phí vận hành mới.

Nếu một điều kiện quan trọng không còn đúng, kết quả tối ưu có thể biến mất hoặc đảo chiều.

**Ví dụ:** chuyển từ `List.contains` sang `HashSet.contains` có thể giảm chi phí tìm kiếm khi tập dữ liệu lớn và có nhiều lần tra cứu. Nhưng nếu phải tạo `HashSet` mới cho mỗi lần tìm trên danh sách chỉ có vài phần tử, tổng thời gian và lượng cấp phát có thể tăng.

Vì vậy, câu hỏi đúng không phải “`HashSet` có nhanh hơn `List` không?” mà là **“với kích thước dữ liệu, tần suất truy vấn, đặc tính phần tử và ngân sách bộ nhớ của hệ thống này, phương án xây `HashSet` có đem lại lợi ích tổng thể không?”**

## 2. Phân biệt dữ kiện, giả thiết và kết luận về hiệu năng

Khi mô tả một tối ưu, cần tách rõ ba loại phát biểu.

| Loại | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Dữ kiện đã đo** | “Trong đợt thử có 10.000 mã hàng và 200 lần tra cứu mỗi lượt xử lý” | Quan sát thuộc tập dữ liệu, thời gian và môi trường đã ghi |
| **Giả thiết** | “Trong ba tháng tới, mỗi lượt thường tra cứu ít nhất 100 mã hàng trên cùng một danh mục” | Điều được kỳ vọng nhưng có thể thay đổi |
| **Lập luận kỹ thuật** | “Xây tập hợp tốn chi phí ban đầu nhưng tra cứu kỳ vọng nhanh hơn trên tập lớn” | Lý do phương án có thể có lợi dưới các điều kiện |
| **Kết quả kiểm chứng** | “Trong benchmark cùng môi trường, phương án B giảm p95 thời gian của bước tra cứu theo ngưỡng chấp nhận” | Bằng chứng thu được cho một phạm vi thử cụ thể |
| **Quyết định** | “Dùng tập hợp cho batch đọc nhiều lần, giữ cách cũ cho thao tác tra cứu đơn lẻ” | Lựa chọn được đưa ra từ yêu cầu, số đo và đánh đổi |

**Dữ kiện đo ngày hôm nay không tự biến thành bảo đảm cho ngày mai.** Phải lưu phạm vi số liệu: phiên bản mã, dữ liệu, cấu hình JVM, mức tải, hạ tầng, cách đo và thời điểm lấy mẫu. Không nên trộn dữ kiện từ máy phát triển với kết luận khẳng định về sản xuất.

Một phát biểu như “thuật toán này có Big-O tốt hơn” là lập luận có giá trị, nhưng **không tự chứng minh** độ trễ thực tế thấp hơn với kích thước đầu vào hiện có. Big-O không nói đầy đủ về hằng số, cấp phát, cache CPU, I/O, GC hoặc tải từ các tác vụ khác.

## 3. Những giả thiết thường quyết định lợi ích tối ưu

| Nhóm giả thiết | Câu hỏi cần trả lời | Ví dụ điều kiện làm tối ưu mất lợi ích |
| --- | --- | --- |
| **Khối lượng đầu vào** | Dữ liệu thường, p95 và cực đại lớn bao nhiêu? | Dữ liệu luôn nhỏ, chi phí chuẩn bị lớn hơn phần tiết kiệm |
| **Tần suất và mô hình truy cập** | Đọc nhiều hay ghi nhiều, lặp lại hay một lần? | Xây index cho một lần tìm duy nhất |
| **Đặc điểm dữ liệu** | Dữ liệu phân bố ra sao, có trùng lặp, dễ băm, được sắp thứ tự? | Hash kém hoặc thay đổi liên tục |
| **Nút thắt thực tế** | CPU, database, mạng, disk, lock hay bộ nhớ đang giới hạn hệ thống? | Tối ưu CPU trong khi hầu hết thời gian chờ mạng |
| **Mức đồng thời** | Có bao nhiêu request/task cùng chạy? | Tăng số thread gây tranh chấp kết nối hoặc lock |
| **Giới hạn bộ nhớ** | Heap, container memory, off-heap và GC còn dư địa? | Cache lớn gây GC và OOM |
| **Độ tươi và tính đúng đắn** | Có được phép dùng dữ liệu cũ hay kết quả gần đúng? | Cache dùng cho giá hoặc hạn mức cần cập nhật tức thời |
| **Chi phí làm mới** | Khi dữ liệu đổi, mất bao nhiêu công để xây lại chỉ mục? | Dữ liệu cập nhật liên tục, rebuild quá thường xuyên |
| **Điều kiện triển khai** | Có đủ CPU, I/O, connection pool và quota ở môi trường thật? | Tối ưu chỉ hiệu quả trên máy đơn không bị giới hạn tài nguyên |
| **Tính ổn định của yêu cầu** | Quy tắc, schema hoặc luồng xử lý thay đổi với nhịp nào? | Cơ chế tối ưu buộc sửa nhiều phần khi yêu cầu mới xuất hiện |

Không nhất thiết ghi một bảng lớn cho mỗi dòng mã. Tập trung vào **giả thiết có thể làm thay đổi quyết định**: nếu nó sai, ta có còn muốn giữ phương án tối ưu hay không?

## 4. Ví dụ Java: xây chỉ mục chỉ có ích khi truy vấn đủ nhiều

Giả sử một tác vụ cần kiểm tra các mã hàng `sku` có thuộc danh mục được phép hay không. Danh mục này được tạo thành một **snapshot** cho mỗi batch; các lần tra cứu của batch dùng cùng snapshot.

Có hai phương án:

- **A — Quét danh sách:** gọi `contains` trên danh sách cho mỗi mã được hỏi.
- **B — Xây chỉ mục:** xây `HashSet` một lần, sau đó gọi `contains` trên tập hợp.

Giả thiết về tính đúng đắn của ví dụ: mã SKU phân biệt chữ hoa/thường; `null` không được chấp nhận; mỗi truy vấn trả một boolean theo đúng thứ tự đầu vào. Các giả thiết này phải giữ nguyên khi thay thuật toán.

### 4.1. Mô hình đầu vào giữ dữ liệu ổn định trong một batch

Ví dụ sử dụng Java 17:

~~~java
import java.util.List;
import java.util.Objects;

record SkuBatch(List<String> allowedSkus,
                List<String> requestedSkus) {
    SkuBatch {
        Objects.requireNonNull(allowedSkus, "allowedSkus");
        Objects.requireNonNull(requestedSkus, "requestedSkus");

        // Chốt snapshot theo cấu trúc; cũng từ chối phần tử null.
        allowedSkus = List.copyOf(allowedSkus);
        requestedSkus = List.copyOf(requestedSkus);
    }
}
~~~

`List.copyOf` bảo đảm các danh sách không thể thay đổi qua API danh sách đã lưu và phần tử `null` không hợp lệ. Vì phần tử ở đây là `String` bất biến, snapshot đủ cho ví dụ. Với phần tử mutable, cần hợp đồng sở hữu dữ liệu và sao chép phù hợp hơn.

### 4.2. Phương án A: quét danh sách

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class SkuLookup {
    static List<Boolean> byScanning(SkuBatch batch) {
        Objects.requireNonNull(batch, "batch");

        List<Boolean> result =
                new ArrayList<>(batch.requestedSkus().size());

        for (String sku : batch.requestedSkus()) {
            result.add(batch.allowedSkus().contains(sku));
        }
        return List.copyOf(result);
    }
}
~~~

Đối với danh sách không có chỉ mục tìm kiếm chuyên dụng, mỗi lần `contains` thường phải kiểm tra một số phần tử đến khi tìm thấy hoặc hết danh sách. Khi danh mục có `n` phần tử và `m` truy vấn, số lần so sánh có thể tăng đến **O(n × m)** trong trường hợp xấu.

Chi phí trên còn phụ thuộc phân bố dữ liệu: nếu phần tử thường nằm ở đầu danh sách, quét có thể dừng sớm. Với danh sách rất nhỏ hoặc một lần tra cứu, cách này dễ hiểu và có thể đủ nhanh.

### 4.3. Phương án B: xây `HashSet` rồi tra cứu

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

final class IndexedSkuLookup {
    static List<Boolean> byIndex(SkuBatch batch) {
        Objects.requireNonNull(batch, "batch");

        Set<String> index = new HashSet<>(batch.allowedSkus());
        List<Boolean> result =
                new ArrayList<>(batch.requestedSkus().size());

        for (String sku : batch.requestedSkus()) {
            result.add(index.contains(sku));
        }
        return List.copyOf(result);
    }
}
~~~

Xây tập hợp thường có chi phí thời gian kỳ vọng **O(n)**, sau đó mỗi lần `contains` có thời gian kỳ vọng gần **O(1)** khi hàm băm và dữ liệu có đặc tính phù hợp. Tổng chi phí kỳ vọng có thể được mô tả gần đúng là **O(n + m)**, đổi lại bộ nhớ bổ sung **O(n)**.

**Không được kết luận `HashSet` luôn nhanh hơn trong thực tế.** Nó cần cấp phát bộ nhớ và xử lý hash, có thể phát sinh GC; va chạm, cách triển khai JVM và phân bố phần tử cũng ảnh hưởng thời gian thực thi. Đặc biệt, khi `m` rất nhỏ, chi phí tạo tập hợp có thể không được bù.

Nếu danh mục thay đổi giữa hai batch, một chỉ mục được giữ lại phải có quy tắc cập nhật/phiên bản. Không nên âm thầm dùng snapshot cũ cho dữ liệu có yêu cầu nhất quán nghiêm ngặt.

### 4.4. Kiểm thử hai phương án giữ cùng hành vi

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;

class SkuLookupTest {
    @Test
    void preservesOrderAndCaseSensitivity() {
        SkuBatch batch = new SkuBatch(
                List.of("A-01", "B-02", "A-01"),
                List.of("A-01", "a-01", "C-03", "B-02"));

        List<Boolean> expected =
                List.of(true, false, false, true);

        assertEquals(expected, SkuLookup.byScanning(batch));
        assertEquals(expected, IndexedSkuLookup.byIndex(batch));
    }

    @Test
    void handlesEmptyCatalogAndQueries() {
        SkuBatch batch = new SkuBatch(
                List.of(), List.of());

        assertEquals(List.of(), SkuLookup.byScanning(batch));
        assertEquals(List.of(), IndexedSkuLookup.byIndex(batch));
    }

    @Test
    void rejectsNullElementWhenSnapshotCreated() {
        assertThrows(NullPointerException.class,
                () -> new SkuBatch(
                        java.util.Arrays.asList("A-01", null),
                        List.of("A-01")));
    }
}
~~~

Unit test này kiểm tra **tính đúng về kết quả**, không chứng minh B nhanh hơn A. Việc tối ưu chỉ được coi là có lợi khi đo hiệu năng phù hợp và xác định được chi phí tài nguyên. Hai lớp cũng có thể được viết trong cùng một đơn vị thực thi Java tùy cách tổ chức dự án.

## 5. Tính điểm hòa vốn của tối ưu bằng giả thiết có thể đo

Đặt:

- `n`: số SKU trong danh mục.
- `m`: số lần kiểm tra SKU trên cùng snapshot.
- `T_scan`: thời gian trung bình cho một lần kiểm tra trên danh sách.
- `T_build`: thời gian xây `HashSet` từ snapshot.
- `T_lookup`: thời gian trung bình cho một lần kiểm tra trên tập hợp.

Mô hình chi phí rất đơn giản:

~~~text
T_A ≈ m × T_scan

T_B ≈ T_build + m × T_lookup

B có lợi về thời gian nếu:
m × T_scan > T_build + m × T_lookup
~~~

Nếu `T_scan > T_lookup`, số lần truy vấn hòa vốn gần đúng là:

`m > T_build / (T_scan - T_lookup)`

**Ví dụ giả định thuần túy:** giả sử trên cùng tập dữ liệu và máy thử, xây chỉ mục mất 1 ms; quét danh sách mất trung bình 0,08 ms/lần; tra tập hợp mất 0,005 ms/lần. Khi ấy ngưỡng theo mô hình là khoảng **13,33 lần truy vấn**, tức từ **14 lần** trở lên B mới bắt đầu có lợi về thời gian kỳ vọng.

Đây **không phải kết quả benchmark** và không phải ngưỡng có thể áp dụng vào mọi dự án. Kết quả thật còn chịu ảnh hưởng của phân bố giá trị trúng/không trúng, kích thước dữ liệu, allocation, GC, biến động tải và hằng số thực thi. Mô hình cũng chưa cộng chi phí tạo snapshot, vốn được hai phương án cùng dùng trong ví dụ.

Điều quan trọng là lập luận giúp đặt **câu hỏi đo đạc đúng**: m thực tế bao nhiêu, chi phí build có thể tái sử dụng bao nhiêu lượt, dữ liệu thay đổi với tần suất nào, và bộ nhớ có đủ không?

### 5.1. Những thay đổi làm quyết định đảo chiều

| Nếu giả thiết thay đổi | Tác động đến lựa chọn |
| --- | --- |
| `m` giảm còn 1–2 truy vấn/batch | Chi phí xây `HashSet` có thể không đáng |
| `n` tăng mạnh, `m` vẫn lớn | Lợi thế thuật toán của chỉ mục có thể tăng |
| Dữ liệu danh mục sửa liên tục | Chi phí xây lại hoặc đồng bộ chỉ mục tăng |
| Nhiều batch dùng chung một danh mục bất biến | Có thể tái sử dụng chỉ mục, nhưng phải rõ phiên bản và vòng đời |
| Heap bị giới hạn, GC tăng | Chi phí bộ nhớ có thể lấn át lợi ích CPU |
| Phần lớn SKU cần tra nằm ở đầu danh sách rất ngắn | Quét tuyến tính có thể đủ tốt dù độ phức tạp lý thuyết kém hơn |
| `equals` hoặc `hashCode` không phù hợp | Tính đúng đắn và chi phí tra cứu có thể bị ảnh hưởng |

**Điều kiện xem lại** nên gắn với những thay đổi như trên chứ không chỉ ghi “sẽ tối ưu thêm khi chậm”.

## 6. Kiểm chứng tối ưu: đo trước và sau trên cùng giả thiết

Một phép đo hữu ích phải cho biết **đã chạy tải gì, trong điều kiện nào, đo điều gì, và kết quả biến động ra sao**. Ví dụ, so sánh A và B trên một danh sách toàn mã trùng không phản ánh danh mục có độ đa dạng lớn.

### 6.1. Chọn workload đại diện

Đối với bài toán tìm SKU, nên bao gồm:

1. **Kích thước danh mục:** nhỏ, điển hình, p95 và lớn nhất có cơ sở.
2. **Số lần tra cứu/batch:** 1, vài lần, hàng chục, hàng trăm tùy dữ liệu thật.
3. **Tỷ lệ tìm thấy:** không trúng, trúng nhiều, trúng ở đầu/cuối khi quét.
4. **Độ trùng lặp:** SKU danh mục có trùng hay không; yêu cầu nghiệp vụ dùng tập hợp hay danh sách.
5. **Phân bố đầu vào:** độ dài chuỗi, ký tự, phân bố hash và tính lặp lại.
6. **Tần suất cập nhật:** chỉ mục có được xây một lần hoặc phải xây lại thường xuyên?
7. **Mức tải và đồng thời:** một luồng hay nhiều batch cùng xử lý, có tranh chấp tài nguyên không?

Không được tối ưu cho một tập dữ liệu quá đẹp hoặc cố ý khác xa sản xuất rồi suy rộng kết quả.

### 6.2. Đo đúng thứ cần cải thiện

| Thước đo | Khi nào cần | Điểm dễ hiểu nhầm |
| --- | --- | --- |
| **Latency mỗi request/batch** | Quan trọng với thời gian phản hồi người dùng | Trung bình đẹp có thể che p95/p99 xấu |
| **Throughput** | Job xử lý lượng lớn, dịch vụ có tải đồng thời | Tăng throughput có thể làm hàng đợi và latency tăng |
| **CPU time / utilization** | Tối ưu tính toán | CPU giảm không đồng nghĩa toàn luồng nhanh hơn nếu I/O chi phối |
| **Allocation rate, peak heap** | Đánh giá index, cache, bản sao dữ liệu | Tối ưu thời gian có thể làm tăng áp lực GC |
| **GC pause và tần suất GC** | Hệ thống Java bị giới hạn bộ nhớ | Một phép chạy ngắn có thể chưa phản ánh GC khi tải dài |
| **I/O, số query, tải database** | Batching, cache, thay truy vấn | Giảm số query nhưng tăng dữ liệu trả về có thể vẫn chậm |
| **p50/p95/p99** | Quan sát phân bố độ trễ | Cần mẫu đủ lớn, định nghĩa cửa sổ và cùng điều kiện tải |
| **Tỷ lệ lỗi, timeout** | Đảm bảo tối ưu không làm mất độ tin cậy | Thành công nhanh hơn không bù lỗi hoặc mất dữ liệu |

Nếu mục tiêu là cải thiện p95 của API, chỉ đo thời gian của hàm `contains` là chưa đủ. Cần xác minh phần tính toán đó **đóng góp đáng kể** vào thời gian toàn yêu cầu và tối ưu thực sự cải thiện kết quả đầu cuối.

### 6.3. Đo đúng cách trong Java

Đo `System.nanoTime()` cho một lần gọi nhỏ dễ bị nhiễu bởi JIT, class loading, GC, tối ưu của JVM, scheduling và hoạt động các tiến trình khác. Benchmark vi mô có thể cần **JMH** để quản lý warm-up, số lần đo, mức song song, trạng thái benchmark và ngăn tối ưu loại bỏ phép tính không được dùng.

Khi làm benchmark:

- Dùng **cùng máy, JVM, phiên bản mã, tham số và dữ liệu** cho hai phương án, hoặc ghi rõ khác biệt.
- Có giai đoạn **warm-up** phù hợp; không so một phương án chạy lạnh với phương án đã được JIT tối ưu.
- **Tiêu thụ kết quả** một cách hợp lệ, tránh phép tính bị JVM loại bỏ vì không quan sát được.
- Lặp phép đo và xem **độ phân tán**, không chỉ chọn lần nhanh nhất.
- Đo **allocation và GC** khi phương án cấp phát cấu trúc mới.
- Tách kết quả **microbenchmark** khỏi tải thực của cả request hoặc batch.
- Tránh benchmark trong khi nhiều tác vụ nặng không kiểm soát cùng chạy trên máy.
- Ghi các giới hạn: một máy thử không đại diện cho mọi cấu hình triển khai.

Bài học này chỉ mô tả phương pháp; không tuyên bố đã chạy benchmark hay có kết quả từ một hệ thống cụ thể.

### 6.4. Một tối ưu phải vượt qua kiểm tra tính đúng đắn

Trước khi công bố cải thiện, cần chạy test xác nhận cùng input cho cùng output theo hợp đồng, đặc biệt các trường hợp biên, dữ liệu thiếu, trùng lặp và lỗi. Các giải pháp có thể nhanh hơn vì **bỏ qua một bước bắt buộc**, nhưng khi đó không phải tối ưu hợp lệ.

## 7. Tối ưu cache: lợi ích phụ thuộc tỷ lệ trúng và độ tươi dữ liệu

Cache thường được đề xuất để giảm độ trễ đọc từ database hoặc API. Tuy nhiên, nó chỉ có lợi nếu có đủ lần đọc lặp, chi phí lấy dữ liệu nguồn đáng kể và chính sách cập nhật phù hợp.

Giả sử:

- `h`: tỷ lệ trúng cache (hit ratio), tính trong workload đang xét.
- `L_hit`: chi phí đọc một lần trúng cache.
- `L_miss`: chi phí một lần miss, bao gồm lấy nguồn dữ liệu và cập nhật cache khi cần.
- `L_overhead`: chi phí điều phối, kiểm tra hoặc đồng bộ bổ sung không nằm trong hai giá trị kia.

Mô hình thời gian trung bình gần đúng:

`E[L_cache] ≈ h × L_hit + (1 - h) × L_miss + L_overhead`

Để cache có lợi về thời gian trung bình, kết quả trên phải **nhỏ hơn đường đọc không cache ở cùng điều kiện**. Còn phải xét độ trễ đuôi, vì nhiều request đồng thời bị miss có thể gây tải đột biến, đặc biệt khi cache hết hạn hàng loạt.

### 7.1. Giả thiết phải ghi khi bật cache

| Giả thiết | Vì sao quan trọng | Điều kiện xem lại |
| --- | --- | --- |
| Tỷ lệ đọc lặp đủ cao | Ít hit thì cache chỉ thêm bước trung gian | Hit ratio thấp hơn mức hòa vốn theo số đo |
| Dữ liệu cho phép độ trễ cập nhật | Dữ liệu cũ có thể vi phạm nghiệp vụ | Có yêu cầu phản ánh giá/tồn kho tức thời |
| Key phản ánh đúng danh tính dữ liệu | Key thiếu tenant/version dễ trả nhầm | Thêm loại người dùng, tenant, phiên bản hoặc cách định danh mới |
| Cache có giới hạn dung lượng | Dữ liệu tích lũy có thể làm tăng heap/GC | Peak memory hoặc eviction vượt ngưỡng vận hành |
| Có chính sách làm mới/invalidation | Giá trị có thể sống quá hạn | Thay đổi nguồn dữ liệu thường xuyên hơn |
| Tải miss được kiểm soát | Miss đồng thời có thể làm nghẽn backend | Tăng timeout, áp lực kết nối hoặc số lần gọi nguồn |
| Dữ liệu cache không chứa thông tin vượt quyền | Cache chung có thể rò dữ liệu giữa người dùng | Thay đổi mô hình phân quyền hoặc phạm vi chia sẻ |

**Tỷ lệ hit cao không tự chứng minh tính đúng đắn**. Một cache trả giá cũ 99% số lần có thể đạt hiệu năng tốt nhưng gây lỗi thanh toán. Mức chấp nhận độ tươi và tính nhất quán phải là ràng buộc rõ ràng, không bị thay thế bằng một con số latency.

### 7.2. Cách ghi điều kiện xem lại thay vì “cache cho nhanh”

> “Bật cache danh mục phiên bản bất biến, giới hạn kích thước theo ngân sách bộ nhớ, khi workload có nhiều lần đọc lặp. Giữ kết quả nếu p95 request cải thiện đáng kể và không tăng lỗi/GC vượt ngưỡng. Xem lại khi cấu trúc key thay đổi, dữ liệu không còn bất biến, hit ratio giảm hoặc độ trễ đuôi tăng khi miss hàng loạt.”

Đây là **mẫu mô tả**, chưa phải thông số sẵn dùng. Mức “đáng kể”, ngưỡng hit ratio, dung lượng và độ trễ phải được xác định bằng yêu cầu cùng số liệu của chính hệ thống.

## 8. Batching và N+1: giảm số chuyến đi, nhưng không gộp vô hạn

Một tác vụ đọc 100 đơn hàng và với mỗi đơn lại truy vấn người mua có thể tạo **một truy vấn danh sách + 100 truy vấn người mua**. Việc gom truy vấn hoặc lấy dữ liệu theo batch có thể giảm overhead mạng và chi phí round-trip.

Lợi ích thường dựa trên các giả thiết:

- Chi phí một lần round-trip đến database đáng kể.
- Nhiều truy vấn có thể gộp theo hợp đồng mà không thay đổi ý nghĩa dữ liệu.
- Kích thước batch không vượt giới hạn tham số, payload, bộ nhớ hoặc thời gian xử lý.
- Các bản ghi được trả về có thể ánh xạ đúng theo khóa, không nhầm tenant hoặc phạm vi quyền.
- Chất lượng query plan, index và tải database vẫn phù hợp.

**Tối ưu không đồng nghĩa batch càng lớn càng tốt.** Một truy vấn quá lớn có thể trả nhiều dữ liệu không cần thiết, tăng bộ nhớ, thời gian giữ kết nối hoặc lock, gây timeout và làm chậm request khác.

Một chính sách batch hợp lý nên ghi: kích thước và phân bố batch hiện tại, thời gian thực thi, số truy vấn giảm, tải DB, giới hạn nguồn và điều kiện xem lại khi dữ liệu tăng. Với đường ghi, thêm giao dịch và xử lý thất bại một phần vào đánh giá.

## 9. Song song hóa: lợi ích phụ thuộc nút thắt và giới hạn tài nguyên

Chuyển vòng lặp tuần tự thành tác vụ song song có thể giảm thời gian hoàn thành khi công việc độc lập và có tài nguyên nhàn rỗi. Nhưng tăng số worker cũng tăng số yêu cầu đồng thời đến database, API đối tác, disk hoặc cùng một lock.

Một số giả thiết cần xác minh:

- Các tác vụ **độc lập** hoặc có mô hình đồng bộ rõ ràng.
- Công việc thuộc loại CPU-bound hay I/O-bound; có bao nhiêu tài nguyên thực dùng được?
- Pool kết nối và quota của các phụ thuộc có chịu nổi mức đồng thời mới?
- Kết quả có cần giữ thứ tự hoặc tính quyết định không?
- Retry, timeout và cancel có thể làm tác dụng phụ lặp không?
- Hàng đợi tác vụ có giới hạn, tạo **backpressure** khi tải tăng không?

**Ví dụ:** dịch vụ có pool database tối đa 10 kết nối. Việc tăng executor từ 10 lên 100 worker không tạo thêm 90 kết nối DB. Nó có thể chỉ làm nhiều task chờ, tăng bộ nhớ hàng đợi và độ trễ đuôi.

Khi ghi quyết định song song hóa, nên nêu rõ **mức đồng thời đang thử**, **ngân sách tài nguyên**, **tải của hệ thống phụ thuộc** và **ngưỡng dừng/mở rộng**. Không chỉ báo “throughput cao hơn” mà bỏ qua p99, tỷ lệ timeout và sức khỏe của thành phần phía sau.

## 10. Tối ưu thời gian có thể làm tăng chi phí bộ nhớ và vận hành

Một cấu trúc dữ liệu giúp tra cứu nhanh hơn nhưng tốn RAM hơn; một cache giảm I/O nhưng giữ nhiều đối tượng sống lâu; một pipeline song song giảm thời gian của một batch nhưng tạo thêm luồng, buffer và hàng đợi.

| Tối ưu | Lợi ích có thể có | Chi phí cần theo dõi |
| --- | --- | --- |
| `HashSet` thay quét danh sách | Tra cứu kỳ vọng nhanh khi nhiều lần tìm | Chi phí xây index, bộ nhớ O(n), GC |
| Cache kết quả | Giảm số lần lấy dữ liệu nguồn | Bộ nhớ, dữ liệu cũ, invalidation, cache stampede |
| Batch truy vấn | Giảm round-trip và số lần gọi DB | Payload lớn, query plan, thời gian khóa/kết nối |
| Xử lý song song | Tăng thông lượng hoặc giảm batch duration | Tranh chấp, queue, tài nguyên phụ thuộc, khó tái hiện |
| Giữ dữ liệu trong bộ nhớ | Tránh đọc/parse lặp | Heap, giới hạn container, mất dữ liệu khi restart |
| Dùng thuật toán ít cấp phát | Giảm áp lực GC | Có thể tăng độ phức tạp và rủi ro sửa lỗi |
| Precompute/bảng tra | Giảm thời gian tính lặp | Dung lượng, chi phí làm mới và đồng bộ phiên bản |

Trong JVM, cần phân biệt **heap**, **off-heap/native memory**, bộ nhớ stack và giới hạn tổng của container. Heap còn dư không có nghĩa tiến trình không thể bị hệ điều hành hoặc container kết thúc vì vượt tổng bộ nhớ. Khi tối ưu, đo **peak memory** và allocation trong workload đại diện thay vì chỉ xem kích thước biến hay `Runtime.freeMemory()` tại một thời điểm.

**Hiệu quả tài nguyên** có thể tính bằng công sức vận hành và năng lực hệ thống, không chỉ tốc độ. Một tối ưu cần thêm cluster cache, cơ chế làm mới, cảnh báo và quy trình phục hồi có thể không đáng nếu latency ban đầu đã đáp ứng mục tiêu.

## 11. Giả thiết về dữ liệu, độ ổn định và tính đúng đắn

Một tối ưu đáng tin phải **giữ hành vi quan sát được theo hợp đồng**, trừ khi yêu cầu chủ động cho phép một mức xấp xỉ hoặc độ trễ cập nhật.

Ví dụ:

- Dùng `HashSet` để kiểm tra **có thuộc tập hợp** có thể phù hợp, nhưng dùng tập hợp thay danh sách **cần giữ thứ tự và số lần xuất hiện** sẽ làm thay đổi ngữ nghĩa.
- Cache thông tin sản phẩm có thể phù hợp cho **mô tả ít đổi**, nhưng có thể không phù hợp cho **số dư hoặc hạn mức giao dịch** cần xác thực tại thời điểm cập nhật.
- Batching giúp giảm round-trip nhưng phải giữ đúng **thứ tự dữ liệu nếu hợp đồng yêu cầu**, quyền truy cập từng bản ghi và ngữ nghĩa transaction.
- Parallel stream có thể thay đổi **thứ tự tác dụng phụ**; không được dùng nếu nghiệp vụ phụ thuộc thứ tự mà chưa có cơ chế bảo đảm.
- Dùng giá trị ước lượng để tăng tốc có thể hữu ích trong gợi ý sản phẩm, nhưng không được tự ý áp dụng cho số tiền phải thanh toán.

Khi viết giả thiết, cần ghi **những bất biến không được phá vỡ** bên cạnh lợi ích kỳ vọng. Điều này giúp ngăn tình huống kết quả chạy nhanh hơn vì đã bỏ qua kiểm tra, xử lý ít dữ liệu hơn hoặc trả thông tin không đủ mới.

## 12. Đặt quyết định tối ưu trong bối cảnh end-to-end

Giả sử một endpoint có p95 là 280 ms, trong đó bước tra cứu SKU bằng danh sách chỉ chiếm phần rất nhỏ, còn phần lớn thời gian chờ DB.

Chuyển từ danh sách sang tập hợp có thể giảm thời gian của bước nhỏ đó, nhưng **không nhất thiết làm p95 của endpoint giảm đáng kể**. Tối ưu một đoạn mã không nằm trên đường găng cũng có thể không tạo lợi ích thấy được cho người dùng.

Phân tích bottleneck có thể dùng:

~~~mermaid
flowchart TD
    A[Đặt mục tiêu end-to-end] --> B[Đo baseline có bối cảnh]
    B --> C[Xác định nút thắt và chi phí chính]
    C --> D[Viết giả thiết khiến tối ưu có lợi]
    D --> E[Chọn thay đổi tối thiểu và bảo vệ tính đúng]
    E --> F[Benchmark và kiểm thử tải đại diện]
    F --> G{Đạt mục tiêu mà không phá ràng buộc?}
    G -- Không --> H[Giữ baseline hoặc sửa giả thiết]
    G -- Có --> I[Áp dụng có quan sát và rollback]
    H --> C
    I --> J[Theo dõi điều kiện xem lại]
    J --> K{Bối cảnh thay đổi?}
    K -- Có --> C
    K -- Không --> J
~~~

**Amdahl's law** nhắc rằng khi một phần công việc chiếm tỷ lệ nhỏ trong tổng thời gian, tối ưu phần đó chỉ có giới hạn tác động đến toàn bộ luồng. Tuy nhiên, các hệ thống có tải đồng thời và hàng đợi có thể có hành vi phi tuyến: giảm chút thời gian ở một nút thắt đang sát bão hòa đôi khi tạo tác động lớn hơn dự kiến. Vì vậy, mô hình lý thuyết cần được đối chiếu bằng đo đạc end-to-end.

Nếu SLO đã được đáp ứng ổn định, không nên mặc nhiên tăng độ phức tạp chỉ để giảm vài microsecond. Có thể ưu tiên cải thiện độ tin cậy, rủi ro bộ nhớ hoặc khả năng bảo trì.

## 13. Ghi quyết định tối ưu theo mẫu có thể kiểm chứng

Một bản ghi tối ưu không cần dài, nhưng phải đủ thông tin để người khác biết **tại sao cách này có lợi** và **khi nào không còn phù hợp**.

~~~markdown
# OPT-007 — <tên tối ưu>
Trạng thái: Đề xuất / Đã chấp nhận / Cần xem lại / Đã thay thế
Ngày, chủ sở hữu và phạm vi áp dụng:

Mục tiêu:
- Luồng hoặc thao tác cần cải thiện:
- Thước đo/SLO và điều không được làm xấu đi:

Baseline:
- Phiên bản mã, môi trường, cấu hình JVM:
- Kích thước và phân bố dữ liệu, mức đồng thời:
- Độ trễ / throughput / CPU / memory / lỗi trước tối ưu:
- Nguồn số liệu, thời gian và độ tin cậy:

Giả thiết khiến tối ưu có lợi:
- A1: <quy mô hoặc tần suất có thể kiểm chứng>
- A2: <mô hình đọc/ghi hoặc khả năng tái sử dụng>
- A3: <ngân sách CPU, I/O, heap hoặc quota>
- A4: <hợp đồng dữ liệu và tính đúng đắn phải giữ>

Phương án:
- Cách thực hiện và điểm thay đổi:
- Chi phí mới: bộ nhớ, phức tạp, GC, vận hành:
- Phương án giữ nguyên và phương án thay thế:

Bằng chứng:
- Benchmark/test dùng cùng workload và môi trường:
- Kết quả trước/sau và độ biến động:
- Kiểm thử tính đúng đắn, trường hợp biên và lỗi:
- Giới hạn của kết luận:

Quyết định:
- Có áp dụng không? Tại sao?
- Cách triển khai an toàn, theo dõi và quay lui:

Điều kiện xem lại:
- Metric/ngưỡng/sự kiện nào làm giả thiết có thể sai?
- Ai theo dõi, nguồn đo và mốc rà soát?
- Khi kích hoạt sẽ kiểm tra và quyết định gì?
~~~

Các số liệu và ngưỡng phải có **đơn vị** và **khoảng thời gian**. “Cache đạt 90%” chưa đủ: là 90% hit trên request nào, trong giờ cao điểm hay cả tuần, với tập dữ liệu nào? “Giảm 20%” chưa đủ nếu không biết baseline, p50 hay p95 và độ biến động phép đo.

### 13.1. Ví dụ bản ghi quyết định cho bài toán SKU

**Đề xuất:** thay quét danh sách bằng chỉ mục `HashSet` trong batch nhiều lần tra cứu.

**Giả thiết:** batch thường tra cứu nhiều mã SKU trên một snapshot ổn định; lượng bộ nhớ bổ sung đủ nhỏ; việc kiểm tra membership không phụ thuộc thứ tự hoặc số lần xuất hiện.

**Bằng chứng cần thu:** phân bố `n` và `m`, thời gian build, thời gian tra cứu cả batch, allocation/GC, tỷ lệ tìm thấy, kết quả giống nhau giữa hai thuật toán. Chưa có benchmark thật thì **trạng thái vẫn là giả thuyết**, không gọi là tối ưu đã được chứng minh.

**Điều kiện xem lại:** số lần truy vấn/batch giảm, snapshot đổi quá thường xuyên, heap áp lực, hoặc chức năng chuyển sang cần bảo toàn thứ tự/tần suất phần tử.

**Lựa chọn có thể xảy ra:** dùng scan cho đường ít tra cứu và dùng chỉ mục cho batch có lợi theo số đo. Không cần ép toàn bộ hệ thống dùng cùng một cấu trúc chỉ vì một luồng được cải thiện.

### 13.2. Ví dụ bản ghi cho cache ở dịch vụ đọc

**Đề xuất:** cache dữ liệu danh mục theo phiên bản để giảm truy vấn tới nguồn.

**Giả thiết:** phiên bản dữ liệu bất biến trong thời gian hiệu lực, nhiều request cùng tra khóa, hit ratio đủ cao, và ngân sách bộ nhớ cho phép.

**Bằng chứng cần thu:** phân bố hit/miss, p95/p99 cả API, mức sử dụng bộ nhớ, GC, số query DB, độ tươi dữ liệu, tải miss đồng thời.

**Điều kiện xem lại:** API bắt đầu yêu cầu dữ liệu gần thời gian thực, thay đổi khóa chứa tenant hoặc quyền, cache stampede, hoặc độ trễ trên đường miss vượt ngưỡng. Nếu những điều kiện này xuất hiện, phải đánh giá lại cache **trước khi** tiếp tục mở rộng dung lượng.

## 14. Những sai lầm thường gặp

**“Big-O tốt hơn nên chắc chắn nhanh hơn.”** Không đúng với mọi kích thước và môi trường. Độ phức tạp tiệm cận không thể thay thế phép đo chi phí chuẩn bị, cấp phát và thời gian thực.

**“Đã benchmark trên laptop nên production cũng nhanh tương tự.”** Chưa đủ. CPU, bộ nhớ, GC, mạng, dữ liệu, mức đồng thời và giới hạn container có thể khác. Cần đo với workload và môi trường đại diện.

**“Cache hit ratio cao nghĩa là tối ưu thành công.”** Không đủ. Cache có thể trả dữ liệu cũ hoặc không cải thiện p95 nếu đường miss và backend quá chậm. Cần kiểm tra cả hợp đồng và kết quả end-to-end.

**“Tăng số thread luôn tăng throughput.”** Không. Nhiều worker có thể làm tăng tranh chấp, thời gian chờ kết nối, queue và lỗi timeout.

**“Giảm thời gian chạy là đủ, không cần đo bộ nhớ.”** Sai. Tăng allocation có thể tạo áp lực GC hoặc vượt giới hạn bộ nhớ ở tải cao.

**“Chỉ cần đo trung bình.”** Không phù hợp khi người dùng quan tâm độ trễ đuôi, hoặc lỗi xuất hiện trong giờ cao điểm. Cần chọn phân vị và thời gian đo theo mục tiêu.

**“Tối ưu một hàm nhỏ tức là đã tối ưu cả hệ thống.”** Không nhất thiết. Phải chứng minh hàm đó ảnh hưởng đáng kể tới thời gian hoặc tài nguyên của luồng được ưu tiên.

**“Điểm benchmark đẹp hơn có thể bù kết quả sai.”** Không. Một tối ưu vi phạm hợp đồng dữ liệu, bảo mật hoặc khả năng khôi phục không được coi là cải thiện chất lượng hợp lệ.

**“Giả thiết đã đúng khi viết code thì không cần xem lại.”** Không. Quy mô, tải, môi trường, quyền truy cập và yêu cầu nghiệp vụ đều có thể đổi.

**“Tối ưu thì càng nhiều cache/index càng tốt.”** Không. Mỗi cấu trúc có chi phí xây, làm mới, giữ bộ nhớ, vận hành và độ phức tạp khi thay đổi.

**“Một ngưỡng đẹp là bằng chứng.”** Ngưỡng tùy ý không phản ánh yêu cầu. Phải gắn ngưỡng với SLO, ngân sách tài nguyên, dữ liệu đo hoặc hạn chế nghiệp vụ có căn cứ.

**“Không có cảnh báo hiệu năng thì chắc chắn không cần đo.”** Phân tích tĩnh có thể bỏ qua đường găng runtime, tranh chấp, dữ liệu và hệ thống bên ngoài. Profiling và đo đạc phải theo mục tiêu vận hành.

## 15. Bài tập vận dụng

### Tình huống A — `HashSet` cho một truy vấn

Ứng dụng kiểm tra một SKU duy nhất trên danh mục 12 phần tử. Lập trình viên xây `HashSet` mới ngay trước mỗi lần `contains`.

**Câu hỏi:** giả thiết nào có thể khiến tối ưu không đáng?

**Gợi ý:** số truy vấn `m = 1` và danh mục nhỏ làm chi phí xây index khó được bù. Nên giữ scan nếu đáp ứng mục tiêu hoặc đo để quyết định, thay vì suy từ Big-O.

### Tình huống B — Cache danh mục có giá thay đổi

Một trang bán hàng thêm cache để giảm p95 từ nguồn dữ liệu. Cache có hit ratio tốt, nhưng giá thay đổi trong lúc khách xác nhận mua hàng.

**Câu hỏi:** tại sao số đo hiệu năng chưa đủ để giữ cache?

**Gợi ý:** cần hợp đồng về độ tươi và giá áp dụng tại thời điểm thanh toán. Cache có thể phù hợp cho hiển thị, nhưng bước chốt giao dịch cần dùng phiên bản giá đã được xác thực theo quy tắc nghiệp vụ. Không cho phép tốc độ làm sai số tiền.

### Tình huống C — Parallel batch làm database chậm

Một job xử lý nhanh hơn khi tăng từ 2 lên 8 worker, nhưng chậm đi khi tăng từ 8 lên 32 worker; p99 của API khác cũng xấu hơn.

**Câu hỏi:** giả thiết nào đã sai hoặc chưa được ghi?

**Gợi ý:** database, connection pool hoặc I/O phía sau có thể đã bão hòa. Phải đo tải phụ thuộc, queue, số kết nối và latency của các dịch vụ khác; tối ưu chỉ hợp lệ nếu không vi phạm ngân sách tài nguyên dùng chung và SLO liên quan.

### Tình huống D — Benchmark chạy nhanh nhưng GC tăng

Phiên bản mới giữ một chỉ mục lớn trong heap. Thời gian CPU của thao tác tra cứu giảm, nhưng hệ thống bị dừng GC dài hơn khi tải cao.

**Câu hỏi:** cần đo thêm gì?

**Gợi ý:** allocation, heap đỉnh, tần suất/pause GC, p95/p99 end-to-end và mức đồng thời. Lợi ích CPU phải được so với chi phí bộ nhớ và trải nghiệm người dùng thực.

### Tình huống E — Tối ưu sau khi nhu cầu thay đổi

Một dịch vụ từng xử lý 100 truy vấn cho mỗi snapshot. Sau khi đổi sản phẩm, mỗi request chỉ còn một truy vấn; mã vẫn xây chỉ mục cho từng request.

**Câu hỏi:** quyết định ban đầu sai hay chỉ hết phù hợp?

**Gợi ý:** có thể quyết định ban đầu hợp lý theo dữ kiện cũ. Nên xem lại khi `m` giảm dưới điểm hòa vốn, đo phương án hiện tại so với scan và ghi quyết định mới. Lịch sử giả thiết giúp hiểu **tại sao cần đổi** mà không đổ lỗi cho lựa chọn cũ.

## 16. Checklist trước khi chốt một tối ưu

- **Mục tiêu:** muốn giảm p95, tăng throughput, giảm CPU, tiết kiệm RAM hay chi phí vận hành?
- **Baseline:** có số đo trước tối ưu trong môi trường và workload được mô tả không?
- **Nút thắt:** thành phần định sửa có thực sự ảnh hưởng đến mục tiêu end-to-end?
- **Giả thiết:** lợi ích phụ thuộc vào kích thước, tần suất, độ lặp dữ liệu, ổn định snapshot và đồng thời nào?
- **Điểm hòa vốn:** có chi phí xây/làm mới, cấp phát hoặc đồng bộ nào phải được bù?
- **Bộ nhớ:** heap, GC, off-heap và giới hạn container có còn đủ dư địa?
- **Tính đúng:** kết quả, thứ tự, trùng lặp, quyền và độ tươi dữ liệu có giữ nguyên theo hợp đồng không?
- **Kiểm chứng:** hai phương án được đo trên cùng điều kiện, nhiều lần và có dữ liệu đủ đại diện?
- **Rủi ro vận hành:** phương án mới có thêm cache, queue, chính sách invalidation hoặc phụ thuộc cần theo dõi?
- **Quay lui:** nếu p99, lỗi hoặc GC xấu đi sau triển khai, có cách trở về baseline?
- **Điều kiện xem lại:** biết rõ metric/ngưỡng/sự kiện nào khiến giả thiết không còn đúng, ai chịu trách nhiệm rà soát?

**Ghi lại giả thiết khiến một tối ưu có lợi** là cách biến nhận định “nhanh hơn” thành quyết định kỹ thuật có thể kiểm chứng. Một tối ưu tốt không chỉ cải thiện con số cục bộ mà còn giữ tính đúng đắn, phù hợp với ngân sách tài nguyên và dễ được đánh giá lại khi workload thay đổi. Trong **CODE_QUALITY_FUNDAMENTALS**, đó là cách xây dựng mã **đáng tin cậy khi vận hành, dễ hiểu về lý do thiết kế và dễ thay đổi khi bối cảnh hiệu năng không còn như trước**.
