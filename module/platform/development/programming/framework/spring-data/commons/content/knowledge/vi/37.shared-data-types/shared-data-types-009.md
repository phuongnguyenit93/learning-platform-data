# Ý nghĩa điểm cao/thấp và sự chuẩn hóa phụ thuộc hàm chấm điểm

Hai kết quả tìm kiếm có điểm 0,2 và 0,8 chưa đủ để quyết định kết quả nào tốt hơn. Nếu đó là cosine similarity theo quy ước thông thường, 0,8 thể hiện mức tương đồng cao hơn. Nếu đó là một khoảng cách cần tối thiểu hóa, 0,2 lại là kết quả gần hơn. Cùng một số trong khoảng từ 0 đến 1 cũng chưa chứng minh đó là xác suất đúng của kết quả.

Trong chương **Kiểu dữ liệu dùng chung** của **Spring Data Commons**, bài học này tập trung vào ngữ nghĩa của điểm trong kết quả truy vấn. Các abstraction dùng chung giúp mang giá trị và kết quả qua các lớp, nhưng ý nghĩa điểm, chiều xếp hạng và phép chuẩn hóa vẫn gắn với hàm chấm điểm, module, backend và cấu hình truy vấn. Không thể chọn ngưỡng hoặc đổi thứ tự chỉ từ tên trường `score`.

## 1. Một điểm cần đi kèm hợp đồng ngữ nghĩa

Khi nhận một giá trị điểm, cần biết ít nhất:

| Thông tin | Câu hỏi |
|---|---|
| Hàm chấm điểm | Đây là cosine similarity, cosine distance, L2, dot product hay điểm khác? |
| Chiều tốt hơn | Giá trị lớn hơn hay nhỏ hơn được ưu tiên? |
| Miền giá trị | Có thể âm không, có bị chặn không, có hữu hạn không? |
| Phép biến đổi | Backend trả giá trị gốc hay một điểm đã được biến đổi? |
| Ngữ cảnh tính | Query, mô hình, dữ liệu và cấu hình nào tạo ra điểm? |
| Chính sách sử dụng | Dùng để xếp hạng, lọc ngưỡng, hiển thị hay kết hợp nhiều nguồn? |

Một field Java kiểu `double` chỉ mang trị số. Một kiểu bao điểm hoặc kết quả tìm kiếm cũng cần được sử dụng theo hợp đồng của hàm chấm điểm và module tương ứng; tên kiểu không tự biến mọi trị số thành cùng một thang đo.

Ví dụ hợp đồng rõ ràng:

```text
function: cosine_similarity
raw score: 0.8
higher is better: true
input vectors: nonzero, cùng không gian embedding
```

Hợp đồng khác:

```text
function: euclidean_distance
raw score: 0.2
higher is better: false
input vectors: cùng số chiều và quy ước dữ liệu
```

Hai trị số không được so sánh trực tiếp như thể chúng đến từ cùng một hàm.

## 2. Điểm tương đồng và khoảng cách có chiều khác nhau

Quy ước thường gặp:

| Đại lượng | Chiều thường dùng | Lưu ý |
|---|---|---|
| Cosine similarity | Cao hơn tốt hơn | Với vector khác 0, giá trị toán học nằm trong [-1, 1] |
| Cosine distance được định nghĩa là `1 - cosine` | Thấp hơn tốt hơn | Theo định nghĩa này, miền toán học là [0, 2] |
| Euclidean/L2 distance | Thấp hơn tốt hơn | Không âm, không có cận trên cố định nếu không ràng buộc dữ liệu |
| Squared L2 distance | Thấp hơn tốt hơn | Bình phương của L2, cùng thứ tự nhưng khác trị số/ngưỡng |
| Dot product | Thường ưu tiên lớn hơn trong bài toán tìm tích vô hướng lớn nhất | Độ lớn vector ảnh hưởng trị số |
| Điểm tìm kiếm văn bản | Thường ưu tiên lớn hơn | Thang điểm phụ thuộc hàm, query và thống kê dữ liệu |

Bảng mô tả các đại lượng đã được định nghĩa rõ. Backend có thể trả một phép biến đổi của chúng, chẳng hạn khoảng cách, âm của tích vô hướng hoặc điểm đã đưa về một khoảng giới hạn.

Do đó, một cấu hình có từ `cosine` trong tên chưa đủ để biết response đang chứa cosine similarity hay một dạng distance được suy ra từ nó.

Cần đọc hợp đồng của thao tác repository/template/backend đang dùng. Không suy ra chiều từ việc field được đặt tên là `score`, `distance`, `rank` hay `similarity` trong DTO của ứng dụng.

## 3. Cosine similarity và cosine distance

Với hai vector khác 0, cosine similarity được định nghĩa:

```text
c = (u · v) / (||u|| × ||v||)
```

Nếu chọn cosine distance theo công thức:

```text
d = 1 - c
```

thì cùng một cặp vector có thể được mô tả bằng hai trị số khác nhau:

| Cosine similarity c | Cosine distance d | Cách hiểu tương đối |
|---:|---:|---|
| 1,0 | 0,0 | Cùng hướng |
| 0,8 | 0,2 | Gần hướng nhau hơn trường hợp c = 0,2 |
| 0,2 | 0,8 | Kém tương đồng hơn trường hợp c = 0,8 |
| 0,0 | 1,0 | Vuông góc trong không gian vector |
| -1,0 | 2,0 | Ngược hướng |

Đây là quan hệ theo định nghĩa toán học đã chọn, không phải lời khẳng định mọi backend trả đúng dạng `1 - c`.

Vector 0 không có cosine similarity xác định theo công thức trên vì mẫu số bằng 0. Cần có chính sách cho dữ liệu này theo mô hình và backend; không tự biến mọi trường hợp thành score 0 rồi coi đó là kết quả hợp lệ.

Sai số số thực có thể làm một giá trị tính toán gần cận hơi lệch miền lý thuyết. Chính sách dung sai phải có chủ đích; không clamp mọi điểm lạ vào [-1, 1] để che việc đang đọc nhầm hàm chấm điểm.

## 4. L2 và L2 bình phương giữ thứ tự nhưng khác ngưỡng

Euclidean distance:

```text
d = sqrt(sum((u_i - v_i)^2))
```

Squared L2:

```text
d_squared = sum((u_i - v_i)^2)
```

Với khoảng cách không âm, phép bình phương giữ thứ tự: khoảng cách nhỏ hơn vẫn có bình phương nhỏ hơn. Tuy nhiên, ngưỡng không được giữ nguyên.

Ví dụ:

```text
d <= 0.5
```

tương ứng với:

```text
d_squared <= 0.25
```

Nếu chuyển backend từ trả L2 sang trả squared L2 mà giữ nguyên ngưỡng 0,5, phạm vi kết quả được chấp nhận đã thay đổi.

Khi vector đều được chuẩn hóa về độ dài 1, có quan hệ:

```text
L2_squared = 2 - 2 × cosine_similarity
```

Ví dụ cosine similarity 0,8 tương ứng squared L2 0,4 và L2 xấp xỉ 0,6325 trong điều kiện đó.

Không dùng công thức này cho vector tùy ý chưa có điều kiện độ dài 1. Quan hệ giữa các hàm phụ thuộc giả thiết về dữ liệu, không chỉ tên trường điểm.

## 5. Chuẩn hóa vector khác chuẩn hóa điểm

Hai thao tác thường bị gọi chung là chuẩn hóa:

| Thao tác | Đối tượng được đổi | Mục tiêu |
|---|---|---|
| Chuẩn hóa vector | Các thành phần hoặc độ dài vector | Đưa vector về một quy ước như unit norm |
| Chuẩn hóa score | Trị số do hàm chấm điểm trả về | Đưa về chiều/thang điểm phù hợp hợp đồng sử dụng |

Với vector unit norm, dot product bằng cosine similarity. Với vector không có điều kiện đó, dot product còn phụ thuộc độ lớn vector và không tự bị giới hạn trong [-1, 1].

Ví dụ một vector cùng hướng nhưng có độ lớn lớn hơn có thể nhận dot product cao hơn, dù góc giữa hai vector không đổi.

Đưa score về [0, 1] sau truy vấn không tự chuẩn hóa vector đầu vào. Ngược lại, chuẩn hóa vector không chứng minh backend đã trả một score trong [0, 1].

Cũng không được đồng nhất chuẩn hóa score tìm kiếm với việc đổi đơn vị của khoảng cách địa lý. Một kiểu khoảng cách có đơn vị km/mile và một điểm khoảng cách trong không gian embedding có hợp đồng khác nhau.

## 6. Không có một công thức chuẩn hóa duy nhất cho mọi score

Giả sử ứng dụng muốn một giá trị càng lớn càng tốt trong [0, 1]. Có nhiều công thức hợp lệ trong những điều kiện khác nhau.

### 6.1. Đưa cosine similarity về [0, 1]

Với `c` trong [-1, 1]:

```text
s = (c + 1) / 2
```

Ví dụ c = 0,8 cho s = 0,9. Công thức giữ thứ tự của cosine similarity.

### 6.2. Đảo chiều khoảng cách không âm

Với `d >= 0`, có thể chọn:

```text
s = 1 / (1 + d)
```

Với khoảng cách hữu hạn, kết quả nằm trong (0, 1]. Khoảng cách nhỏ hơn cho score lớn hơn. Khi d = 0, s = 1.

Đây là một lựa chọn biến đổi, không phải công thức mặc định chung được mọi module Spring Data sử dụng.

### 6.3. Từ cosine distance về cùng thang với mục 6.1

Nếu biết chắc `d = 1 - c`, có thể dùng:

```text
s = 1 - d / 2
```

Với d = 0,2, kết quả là 0,9, nhất quán với `(c + 1) / 2` khi c = 0,8.

Nhưng nếu dùng `1 / (1 + d)` cho cùng d = 0,2, kết quả xấp xỉ 0,8333. Cả hai đều đảo chiều khoảng cách theo cách hữu ích, nhưng cho trị số và ngưỡng khác nhau.

Không gọi chung cả hai là “score chuẩn hóa 0,9” rồi áp dụng cùng một ngưỡng mà không ghi lại công thức.

## 7. Ví dụ Java: đặt tên phép biến đổi theo điều kiện

Các hàm sau là **chính sách minh họa của ứng dụng**, không phải tên API chuyển đổi score bắt buộc của Spring Data:

```java
final class ApplicationScoreNormalization {

    static double cosineSimilarityToUnitInterval(double cosine) {
        requireFinite(cosine);
        if (cosine < -1.0 || cosine > 1.0) {
            throw new IllegalArgumentException(
                    "Cosine similarity phải nằm trong [-1, 1]");
        }
        return (cosine + 1.0) / 2.0;
    }

    static double cosineDistanceToUnitInterval(double distance) {
        requireFinite(distance);
        if (distance < 0.0 || distance > 2.0) {
            throw new IllegalArgumentException(
                    "Ví dụ yêu cầu cosine distance = 1 - cosine, thuộc [0, 2]");
        }
        return 1.0 - distance / 2.0;
    }

    static double nonNegativeDistanceToInverseScore(double distance) {
        requireFinite(distance);
        if (distance < 0.0) {
            throw new IllegalArgumentException(
                    "Phép biến đổi này yêu cầu khoảng cách không âm");
        }
        return 1.0 / (1.0 + distance);
    }

    private static void requireFinite(double value) {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("Điểm phải hữu hạn");
        }
    }
}
```

Tên hàm và kiểm tra miền giúp ngăn việc đưa một score văn bản không có cận trên vào công thức chỉ hợp lệ cho cosine similarity.

Ví dụ cố ý từ chối giá trị ngoài miền. Nếu ứng dụng cho phép sai số nhỏ tại cận, cần định nghĩa chính sách đó riêng và xác định nguồn sai số. Không bỏ toàn bộ kiểm tra chỉ vì backend dùng số thực.

Đặc biệt, phải biết backend đã biến đổi score hay chưa. Nếu một giá trị đã được đưa về [0, 1] lại đi qua công thức `(x + 1) / 2`, thang điểm bị đổi lần nữa và ngưỡng cũ không còn cùng ý nghĩa.

## 8. Giá trị trong [0, 1] không tự là xác suất

Một kết quả có normalized score 0,9 không tự có nghĩa “90% khả năng trả lời đúng” hoặc “90% chắc chắn thuộc cùng chủ đề”.

Một phép biến đổi số học chỉ thay thang đo. Để diễn giải như xác suất cần một mô hình và quá trình hiệu chỉnh/đánh giá phù hợp với biến cố cụ thể, dữ liệu và miền sử dụng.

Các cách diễn đạt cần phân biệt:

```text
Score tương đồng chuẩn hóa: 0.9
```

và:

```text
Xác suất một nhãn đúng: 0.9
```

Cách thứ hai đòi hỏi bằng chứng khác với việc lấy cosine rồi dịch/đổi thang.

Khi hiển thị cho người dùng, nên đặt tên theo ý nghĩa thật như mức tương đồng hoặc điểm xếp hạng. Không đổi nhãn thành độ tin cậy chỉ vì trị số có thể nhân với 100.

Một score tốt cho xếp hạng tương đối trong một truy vấn cũng chưa chắc tốt cho quyết định tự động chấp nhận/từ chối bằng một ngưỡng chung.

## 9. Ngưỡng lọc phải được chuyển cùng công thức

Giả sử hợp đồng yêu cầu cosine similarity ít nhất 0,8:

```text
c >= 0.8
```

Các dạng tương đương theo giả thiết đã nêu:

| Dạng điểm | Điều kiện tương ứng |
|---|---|
| Cosine similarity c | c >= 0,8 |
| Cosine distance d = 1 - c | d <= 0,2 |
| Điểm chuẩn hóa s = (c + 1) / 2 | s >= 0,9 |
| Điểm inverse từ d, s = 1 / (1 + d) | s >= 1 / 1,2, xấp xỉ 0,8333 |
| Squared L2 của vector unit norm | d_squared <= 0,4 |

Không sao chép con số 0,8 sang tất cả các dạng score rồi coi đó là cùng điều kiện.

Với phép biến đổi giảm theo khoảng cách, hướng bất đẳng thức thay đổi khi chuyển sang thang càng lớn càng tốt. Cũng cần xác định có bao gồm đúng cận hay không và dùng giá trị chưa bị làm tròn trong quyết định lọc.

Ngưỡng được đặt ở backend và ngưỡng lọc sau truy vấn có thể tạo hành vi khác nhau về hiệu năng và số lượng kết quả. Nếu chỉ lấy top-k rồi lọc trong bộ nhớ, response có thể còn ít hơn k; bước lọc không tự lấy bù các kết quả chưa được truy hồi.

Khả năng đưa ngưỡng vào truy vấn phụ thuộc module, loại truy vấn và backend. Một abstraction score ở Commons không tự bảo đảm mọi repository có cùng tham số threshold hoặc cùng kiểu kết quả.

## 10. Min-max theo batch làm thay đổi ý nghĩa ngưỡng

Một cách chuẩn hóa điểm càng lớn càng tốt là:

```text
s = (raw - minRaw) / (maxRaw - minRaw)
```

Công thức phụ thuộc tập kết quả đang dùng để tính min và max.

Giả sử ba kết quả có raw score A = 9, B = 8, C = 0:

```text
A → 1
B → 8/9, xấp xỉ 0.889
C → 0
```

Nếu chỉ lấy A và B để chuẩn hóa:

```text
A → 1
B → 0
```

Raw score của B không đổi, nhưng normalized score thay đổi mạnh chỉ vì tập kết quả khác nhau. Một ngưỡng 0,8 ở hai batch không còn diễn đạt cùng mức chất lượng.

Nếu mọi raw score bằng nhau, mẫu số bằng 0. Ứng dụng phải có chính sách cho tình huống đó; không để NaN đi vào JSON hoặc logic quyết định một cách ngầm định.

Min-max vẫn có thể hữu ích cho mục tiêu cụ thể, nhưng cần ghi rõ nó là chuẩn hóa theo tập kết quả. Không dùng nó như bằng chứng rằng điểm của các truy vấn, các trang hoặc các backend đã trở nên so sánh được toàn cục.

## 11. Giữ chiều xếp hạng trong mã ứng dụng

Một hợp đồng ứng dụng minh họa:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

enum ScoreDirection {
    HIGHER_IS_BETTER,
    LOWER_IS_BETTER
}

record ScoreContract(String function, ScoreDirection direction) {

    ScoreContract {
        Objects.requireNonNull(function);
        Objects.requireNonNull(direction);
        if (function.isBlank()) {
            throw new IllegalArgumentException("Phải định danh hàm chấm điểm");
        }
    }
}

record SearchHit(String id, String title, double rawScore) {

    SearchHit {
        Objects.requireNonNull(id);
        Objects.requireNonNull(title);
        if (!Double.isFinite(rawScore)) {
            throw new IllegalArgumentException("Ví dụ chỉ nhận score hữu hạn");
        }
    }
}

final class SearchHitOrdering {

    static List<SearchHit> bestFirst(
            List<SearchHit> hits,
            ScoreContract contract) {

        Comparator<SearchHit> byScore =
                Comparator.comparingDouble(SearchHit::rawScore);

        if (contract.direction() == ScoreDirection.HIGHER_IS_BETTER) {
            byScore = byScore.reversed();
        }

        return hits.stream()
                .sorted(byScore.thenComparing(SearchHit::id))
                .toList();
    }
}
```

Các type trên do ứng dụng tự định nghĩa, không phải chữ ký API được hứa hẹn cho mọi module Spring Data. Ví dụ giả định mọi hit trong danh sách cùng `ScoreContract` và cùng ngữ cảnh có thể so sánh.

Khóa `id` giúp phá hòa theo một quy tắc xác định trong danh sách đã có. Nó không tạo snapshot dữ liệu xuyên nhiều request và không thay chính sách thứ tự của backend khi truy hồi ứng viên.

Hàm chỉ sắp xếp tập đã nhận. Nếu adapter lấy nhầm top-k theo chiều ngược, việc đảo danh sách sau đó không khôi phục được các kết quả tốt đã không được lấy.

Cần thiết kế chiều xếp hạng đúng ngay trong đường truy vấn, rồi dùng mã ứng dụng để duy trì hoặc kiểm chứng hợp đồng khi cần.

## 12. Biên repository và adapter phải giữ metadata điểm

Một port tìm kiếm của ứng dụng có thể trả các hit và mô tả hợp đồng score. Adapter của module có trách nhiệm chuyển kết quả gốc mà không làm mất ngữ nghĩa.

Những điều cần xác định ở adapter:

| Nội dung | Ví dụ câu hỏi |
|---|---|
| Kiểu kết quả module | Điểm nằm trong hit, wrapper hay metadata riêng? |
| Hàm truy vấn | Đang dùng cosine, L2, dot product hoặc hàm backend nào? |
| Chiều trả về | Repository đã xếp tốt nhất trước chưa? |
| Phép biến đổi | Điểm đang là raw distance hay similarity đã đổi thang? |
| Giá trị thiếu | Không có score được biểu diễn thế nào? |
| Giới hạn khả năng | Có hỗ trợ threshold, top-k, paging hoặc tìm kiếm xấp xỉ không? |

Ở những phiên bản/module cung cấp kiểu bao điểm, similarity hoặc kết quả tìm kiếm chuyên dụng, hãy dùng chúng theo metadata và hợp đồng của API tương ứng. Không tự giả định mọi lớp có phương thức `getScore()` giống nhau hoặc mọi hàm chấm điểm có cùng factory/normalizer.

Chỉ kế thừa `Repository` không tự tạo mọi khả năng tìm kiếm vector. Derived query, template, repository fragment và cấu hình index phải phù hợp module đang dùng.

Nếu một kết quả không có score, không tự gán 0 để lấp dữ liệu. Với distance, 0 có thể là giá trị tốt nhất; với một hàm khác, 0 có ý nghĩa khác. Trạng thái không có điểm cần được biểu diễn rõ ràng.

Tương tự, không trả raw score mà bỏ metadata rồi để controller đoán hàm từ tên repository. Đây là một quyết định giao tiếp giữa các lớp cần được duy trì khi thay backend.

## 13. Công bố raw và normalized score rõ ràng

Nếu API cần công khai cả hai dạng, có thể chọn schema minh họa:

```json
{
  "id": "doc-101",
  "title": "Tài liệu A",
  "rawScore": {
    "value": 0.2,
    "function": "cosine_distance_1_minus_cosine",
    "direction": "LOWER_IS_BETTER"
  },
  "normalizedScore": {
    "value": 0.9,
    "transform": "cosine_distance_to_unit_interval_v1",
    "direction": "HIGHER_IS_BETTER"
  },
  "searchConfiguration": "catalog-embedding-v3"
}
```

Đây là schema của ứng dụng, không phải JSON mặc định của mọi kết quả Spring Data. Tên transform diễn đạt công thức `1 - raw / 2` theo quy ước cosine distance đã chọn.

Không nhất thiết endpoint nào cũng phải công khai raw score. Tuy nhiên, các lớp nội bộ và công cụ chẩn đoán cần có đủ ngữ cảnh để hiểu tại sao một kết quả được chấp nhận hoặc xếp trước kết quả khác.

Version của cấu hình có thể gắn với mô hình embedding, cách chuẩn hóa vector, hàm chấm điểm và quy tắc biến đổi. Thay đổi một phần quan trọng của hợp đồng cần được xem xét lại cùng ngưỡng và cách client diễn giải điểm.

Làm tròn response là quyết định biểu diễn. Không dùng giá trị đã làm tròn để thay thế raw score trong logic lọc hoặc để chứng minh hai hit thực sự bằng nhau.

## 14. Không so điểm khác truy vấn/backend bằng một cách máy móc

Một score văn bản 12 từ truy vấn A và score 8 từ truy vấn B không tự chứng minh kết quả của A phù hợp hơn về mặt nghiệp vụ. Tương tự, cosine similarity từ hai mô hình embedding khác nhau không tự có cùng phân bố chất lượng dù cùng miền [-1, 1].

Các thay đổi có thể làm ngưỡng cũ mất ý nghĩa gồm:

- Đổi mô hình embedding hoặc tiền xử lý đầu vào.
- Đổi từ vector có chuẩn hóa độ dài sang vector chưa chuẩn hóa.
- Đổi hàm khoảng cách hoặc dạng score backend trả về.
- Đổi thống kê dữ liệu/index trong tìm kiếm văn bản.
- Đổi phép chuẩn hóa theo batch hoặc cách chọn tập ứng viên.
- Đổi chính sách kết hợp nhiều nguồn xếp hạng.

Nếu kết hợp điểm văn bản và vector bằng một tổng có trọng số, cần hiểu thang đo và mức đóng góp của từng nguồn. Chỉ đổi cả hai về [0, 1] không tự bảo đảm chúng đã được hiệu chỉnh để cộng với nhau như các bằng chứng cùng ý nghĩa.

Một phương án khác là kết hợp thứ hạng thay vì trị số thô, chẳng hạn một chiến lược rank fusion có tham số riêng. Đây vẫn là chính sách tìm kiếm cần được thiết kế/đánh giá, không phải hành vi tự có chỉ vì kết quả mang kiểu score chung.

Tìm kiếm xấp xỉ cũng cần được hiểu riêng: chuẩn hóa điểm không làm tập ứng viên xấp xỉ trở thành tập hàng xóm chính xác toàn cục. Nếu kết quả thay đổi do index hoặc cấu hình truy hồi, một phép đổi thang không khôi phục ứng viên đã bị bỏ sót.

## 15. Tình huống kiểm chứng ngữ nghĩa score

| Tình huống | Điều cần xác minh |
|---|---|
| Hai cosine similarity 0,2 và 0,8 | Theo quy ước này, 0,8 tốt hơn |
| Hai distance 0,2 và 0,8 | Theo quy ước cần tối thiểu hóa, 0,2 tốt hơn |
| Cosine similarity 0,8 được đổi về [0, 1] | Công thức `(c + 1) / 2` cho 0,9 |
| Cosine distance 0,2 theo `1 - c` | Dùng `1 - d / 2` cho 0,9 |
| Cùng d = 0,2 nhưng dùng inverse distance | Kết quả khoảng 0,8333, không phải 0,9 |
| Đổi L2 sang squared L2 | Chuyển ngưỡng, không chỉ giữ cùng con số |
| Backend đã normalize | Không biến đổi lặp lần nữa ngoài chủ đích |
| Min-max với tập top-k khác nhau | Không coi ngưỡng là thước đo chất lượng toàn cục |
| Vector 0 trong cosine | Theo chính sách dữ liệu/backend, không giả điểm hợp lệ |
| Điểm bị thiếu, NaN hoặc vô cực | Biểu diễn/xử lý có chủ đích, không thay bằng 0 |
| Cùng điểm sau làm tròn | Không suy ra raw score hoặc thứ hạng gốc bằng nhau |
| Đổi mô hình/hàm chấm điểm | Đánh giá lại ngưỡng và version hợp đồng |

Khi quan sát lỗi, cần giữ raw score, hàm, chiều xếp hạng và phép biến đổi liên quan. Chỉ ghi một con số cuối cùng có thể không đủ để xác định lỗi nằm ở truy vấn, adapter, normalize hay chính sách threshold.

## 16. Bài tập tự kiểm tra

### Tình huống 1: Luôn sort score giảm dần

Một endpoint nhận raw Euclidean distance nhưng tái sử dụng comparator của similarity.

**Phân tích:** kết quả xa nhất trong tập đã nhận có thể bị đặt trước. Cần giữ chiều tốt hơn trong hợp đồng và cấu hình truy hồi/hiển thị theo đúng chiều đó.

### Tình huống 2: Score 0,9 được hiển thị là 90% chính xác

Score chỉ được tính từ cosine bằng một phép đổi thang tuyến tính.

**Phân tích:** phép đổi thang không tạo xác suất. Cần gọi đúng ý nghĩa như mức tương đồng và chỉ diễn giải xác suất khi có mô hình cùng đánh giá phù hợp.

### Tình huống 3: Đổi cosine similarity sang cosine distance nhưng giữ threshold >= 0,8

Backend mới dùng `d = 1 - c`.

**Phân tích:** hướng và trị số ngưỡng đã sai. Điều kiện `c >= 0,8` tương ứng `d <= 0,2` theo định nghĩa này.

### Tình huống 4: Cùng tài liệu có normalized score khác khi đổi limit

Ứng dụng normalize bằng min-max trên tập kết quả hiện tại.

**Phân tích:** thang điểm phụ thuộc min/max của batch. Đổi số ứng viên có thể đổi score dù raw score giữ nguyên; không dùng ngưỡng đó như một chuẩn cố định xuyên mọi request.

### Tình huống 5: Vector đã chuẩn hóa nên cho rằng mọi score đều trong [0, 1]

Backend trả một đại lượng khác như cosine distance hoặc một score đã biến đổi theo quy ước riêng.

**Phân tích:** chuẩn hóa vector và chuẩn hóa score là hai thao tác khác nhau. Cần biết chính xác hàm và dạng kết quả đang nhận.

### Tình huống 6: Gán 0 cho kết quả không có score

Một adapter muốn tránh giá trị thiếu trong DTO.

**Phân tích:** 0 có thể là khoảng cách tốt nhất hoặc một giá trị hợp lệ khác. Trạng thái thiếu điểm phải được giữ riêng, không biến thành bằng chứng xếp hạng giả.

Một điểm có thể được sử dụng đúng khi ứng dụng giữ đủ hàm chấm điểm, chiều tốt hơn, miền giá trị và phép biến đổi. Hãy duy trì hợp đồng ấy từ module/repository qua service đến API, rồi chọn ngưỡng và cách hiển thị theo cùng ngữ nghĩa thay vì dựa vào trị số đơn lẻ.
