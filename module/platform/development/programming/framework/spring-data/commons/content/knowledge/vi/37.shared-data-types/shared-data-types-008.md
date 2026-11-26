# Score, Similarity và ScoringFunction theo phiên bản

## 1. Một con số chưa đủ để hiểu mức độ liên quan

Một kết quả tìm kiếm có điểm `0.8` chưa cho biết nó tốt hay xấu. Giá trị đó có thể là:

- Khoảng cách, trong đó nhỏ hơn thường gần hơn.
- Độ tương đồng, trong đó lớn hơn thường giống hơn.
- Điểm đã được backend biến đổi từ một phép đo gốc.
- Giá trị chuẩn hóa mà ứng dụng dùng cho một hợp đồng tìm kiếm cụ thể.

Trong chương **Kiểu dữ liệu dùng chung** của module **SPRING_DATA_COMMONS**, ba abstraction giúp giữ lại ngữ cảnh quan trọng này là:

| Kiểu | Vai trò chính |
| --- | --- |
| `Score` | Một giá trị số cùng thông tin về hàm chấm điểm |
| `Similarity` | Một dạng `Score` mang ngữ nghĩa tương đồng chuẩn hóa trong khoảng `[0, 1]` |
| `ScoringFunction` | Mô tả hàm chấm điểm được sử dụng hoặc được yêu cầu |

Chúng thường xuất hiện trong vector search, nhưng việc thực hiện phép tìm kiếm vẫn thuộc module lưu trữ và backend. Các kiểu dùng chung không tự tạo vector index hoặc làm mọi repository hỗ trợ cùng một phép tìm kiếm.

Sau bài học, bạn có thể:

- Xác định mốc phiên bản có các API này.
- Phân biệt raw score với normalized similarity.
- Chọn chiều so sánh và ngưỡng theo ngữ nghĩa của điểm.
- Dùng factory cùng range đúng mục đích.
- Giữ metadata cần thiết khi đưa điểm từ repository ra service hoặc API.

## 2. Mốc phiên bản và package cần dùng

Ba API trong bài thuộc package:

```java
org.springframework.data.domain
```

Import tương ứng:

```java
import org.springframework.data.domain.Score;
import org.springframework.data.domain.Similarity;
import org.springframework.data.domain.ScoringFunction;
```

Chúng được giới thiệu từ **Spring Data Commons 4.0**. Mốc `Since: 4.0` được ghi trong [API Score 4.0.0](https://docs.spring.io/spring-data/commons/docs/4.0.0/api/org/springframework/data/domain/Score.html), [Similarity tại tag 4.0.0](https://raw.githubusercontent.com/spring-projects/spring-data-commons/4.0.0/src/main/java/org/springframework/data/domain/Similarity.java) và [ScoringFunction tại tag 4.0.0](https://raw.githubusercontent.com/spring-projects/spring-data-commons/4.0.0/src/main/java/org/springframework/data/domain/ScoringFunction.java).

| Phiên bản Commons | Cách áp dụng |
| --- | --- |
| Dòng 3.x và các dòng cũ hơn | Không sử dụng ba class/interface mới trong package trên; dùng abstraction của ứng dụng hoặc API riêng mà module đang hỗ trợ |
| Từ 4.0, với API được mô tả trong bài | Có thể dùng `Score`, `Similarity`, `ScoringFunction` và các kiểu liên quan |
| Khi chuyển sang bản khác | Kiểm tra đúng API, overload và tích hợp vector search của module lưu trữ tương ứng |

Một module có thể đã trả điểm tìm kiếm qua API riêng từ trước Commons 4.0. Điều đó không có nghĩa điểm ấy đã là `org.springframework.data.domain.Score`.

Các ví dụ Java dưới đây lấy API ở **tag 4.0.0** làm mốc cụ thể. Không suy ra sự hiện diện của API chỉ từ tên phiên bản Spring Boot hoặc từ một tài liệu `current` đang mô tả dòng khác.

Khi triển khai, cần kiểm tra dependency được resolve và nền tảng quản lý phiên bản. Nâng riêng Commons trong một hệ sinh thái chưa tương thích không phải là bước cấu hình đủ để có vector search hoạt động.

## 3. Score: giá trị và hàm chấm điểm đi cùng nhau

### 3.1. Tạo và đọc Score

```java
ScoringFunction cosine = ScoringFunction.cosine();

Score rawScore = Score.of(0.8, cosine);

double value = rawScore.getValue();
String functionName = rawScore.getFunction().getName();
```

Trong API 4.0, `Score` là value object bất biến. Nó giữ giá trị kiểu `double` và một `ScoringFunction`. Factory trên đóng gói thông tin; nó không tính cosine từ hai vector.

Có thể tạo score không chỉ định hàm:

```java
Score scoreWithoutFunction = Score.of(0.8);
```

Factory một tham số sử dụng `ScoringFunction.unspecified()`. Giá trị này diễn đạt việc chưa có mô tả hàm cụ thể, không phải mặc định chọn cosine hoặc Euclidean.

Thông tin factory và accessor được mô tả trong [API Score](https://docs.spring.io/spring-data/commons/docs/4.0.0/api/org/springframework/data/domain/Score.html).

### 3.2. Không áp cùng miền giá trị cho mọi score

Ví dụ, raw cosine similarity có thể âm với hai vector thực khác không. Trong khi đó, khoảng cách Euclidean thuần túy không âm và có thể lớn hơn 1.

```java
Score rawCosine = Score.of(-0.2, ScoringFunction.cosine());
Score distance = Score.of(2.4, ScoringFunction.euclidean());
```

Hai giá trị trên không mang cùng ngữ nghĩa dù cùng có kiểu `Score`. Không áp một quy tắc chung như “score phải từ 0 đến 1” cho toàn bộ điểm backend trả về.

Trong code ứng dụng, vẫn cần kiểm tra giá trị có hữu hạn và có phù hợp với hợp đồng backend không. Factory value object không thay thế validation nghiệp vụ hoặc việc xác minh metric.

Ví dụ một lớp biên có thể tự yêu cầu:

```java
import java.util.Objects;

static Score finiteScore(double value, ScoringFunction function) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Score phải là số hữu hạn");
    }

    return Score.of(value, Objects.requireNonNull(function));
}
```

Đây là policy của ứng dụng trong ví dụ. Nó không khẳng định mọi backend đều trả cùng miền giá trị.

### 3.3. Score thường là metadata của một lần tìm kiếm

Cùng một tài liệu có thể có điểm khác nhau khi query vector khác nhau. Điểm không nhất thiết là một thuộc tính bền vững của chính entity.

Vì vậy, thường nên giữ điểm trong kết quả tìm kiếm hoặc DTO kết quả, thay vì tự lưu đè vào domain mỗi khi đọc. Các dữ liệu như ID, trạng thái, metadata auditing và điểm liên quan có vòng đời khác nhau.

## 4. ScoringFunction: mô tả phép đo, không phải bộ tính vector tại chỗ

### 4.1. Các factory thường dùng

```java
ScoringFunction euclidean = ScoringFunction.euclidean();
ScoringFunction cosine = ScoringFunction.cosine();
ScoringFunction dotProduct = ScoringFunction.dotProduct();
ScoringFunction unspecified = ScoringFunction.unspecified();
```

Interface cung cấp `getName()` cùng các factory mô tả những lựa chọn phổ biến. API ở mốc 4.0 không có một phương thức như `calculate(vectorA, vectorB)` trên interface này.

Tạo `ScoringFunction.cosine()` không thực hiện truy vấn, không sinh embedding và không tính một ma trận độ tương đồng. Backend hoặc adapter thực thi mới chịu trách nhiệm áp dụng phép đo.

Chi tiết interface có trong [ScoringFunction 4.0.0](https://raw.githubusercontent.com/spring-projects/spring-data-commons/4.0.0/src/main/java/org/springframework/data/domain/ScoringFunction.java).

### 4.2. Các hàm có ngữ nghĩa khác nhau

| Phép đo toán học gốc | Ý nghĩa | Chiều thường dùng để chọn kết quả tốt hơn |
| --- | --- | --- |
| Euclidean distance | Khoảng cách L2 giữa hai vector | Nhỏ hơn |
| Cosine similarity | Mức cùng hướng, độc lập với độ lớn khi đã chia theo chuẩn | Lớn hơn |
| Dot product | Tổng tích từng thành phần, chịu ảnh hưởng của độ lớn | Lớn hơn trong bài toán tối đa hóa inner product |

Bảng nói về phép đo toán học gốc. Backend có thể trả một score đã biến đổi, chẳng hạn từ distance sang một giá trị tăng khi mức liên quan tăng. Phải kiểm tra ý nghĩa giá trị thực tế, không chỉ nhìn tên cấu hình.

Ở tag 4.0.0, enum `VectorScoringFunctions` còn có `TAXICAB` và `HAMMING`, ngoài `EUCLIDEAN`, `COSINE` và `DOT_PRODUCT`:

```java
import org.springframework.data.domain.VectorScoringFunctions;

ScoringFunction hamming = VectorScoringFunctions.HAMMING;
```

Sự hiện diện của constant không bảo đảm module lưu trữ hỗ trợ metric đó trong index hoặc query. Xem [VectorScoringFunctions 4.0.0](https://raw.githubusercontent.com/spring-projects/spring-data-commons/4.0.0/src/main/java/org/springframework/data/domain/VectorScoringFunctions.java).

### 4.3. Mô tả hàm không tự thay cấu hình index

Một score được gắn nhãn cosine không làm index đang cấu hình Euclidean chuyển sang cosine. Tương tự, viết một implementation `ScoringFunction` có tên mới không tự dạy backend cách thực thi phép đo đó.

Cần giữ nhất quán giữa:

- Metric mà index hoặc truy vấn thực sự sử dụng.
- Giá trị backend trả về.
- Cách adapter diễn giải hoặc chuẩn hóa điểm.
- Metadata mà service và client nhận được.

Tên hàm giúp mang ngữ cảnh, nhưng không chứa toàn bộ ngữ cảnh tìm kiếm như embedding model, phiên bản index, bộ dữ liệu và chính sách chuẩn hóa.

## 5. Similarity: một dạng score đã có ngữ nghĩa chuẩn hóa

### 5.1. Miền giá trị và chiều diễn giải

`Similarity` là subclass cuối cùng của `Score`. Ý nghĩa chuẩn của nó là:

```text
0.0: ít tương đồng nhất trên thang đo được sử dụng
1.0: tương đồng cao nhất trên thang đo được sử dụng
```

Factory thông thường:

```java
Similarity similarity = Similarity.of(
        0.9,
        ScoringFunction.cosine());
```

`Similarity.of(...)` kiểm tra giá trị thuộc khoảng `[0, 1]` ở mốc API của bài. Các giá trị ngoài miền bị từ chối bằng `IllegalArgumentException`. Chi tiết có trong [mã nguồn Similarity 4.0.0](https://raw.githubusercontent.com/spring-projects/spring-data-commons/4.0.0/src/main/java/org/springframework/data/domain/Similarity.java).

Ví dụ để phân biệt:

```java
Score raw = Score.of(-0.2, ScoringFunction.cosine());

// Không phù hợp với factory normalized similarity:
// Similarity.of(-0.2, ScoringFunction.cosine());
```

Một raw cosine âm có thể hợp lệ về toán học. Nó cần được diễn giải hoặc biến đổi theo hợp đồng phù hợp trước khi dùng dưới dạng normalized similarity.

### 5.2. of không tự thực hiện chuẩn hóa

Lời gọi:

```java
Similarity.of(0.8, ScoringFunction.euclidean());
```

nhận một giá trị `0.8` đã được hiểu là normalized similarity gắn với hàm được chỉ định. Nó không nhận distance `0.8` rồi tự tính một công thức để đổi distance sang similarity.

Tương tự:

```java
Score.of(0.8, ScoringFunction.cosine());
Similarity.of(0.8, ScoringFunction.cosine());
```

có thể mang cùng giá trị số và mô tả hàm nhưng khác cách diễn giải: một giá trị được đóng gói như score, giá trị kia được khai báo là normalized similarity.

Đừng chuyển raw score thành similarity chỉ bằng cách gọi một constructor/factory khác mà chưa biết backend hoặc adapter định nghĩa thang đo ra sao.

### 5.3. raw bỏ validation, không phải bộ chuyển đổi

API còn có:

```java
Similarity trusted = Similarity.raw(
        0.9,
        ScoringFunction.cosine());
```

Factory `raw` tạo đối tượng mà không chạy validation miền giá trị như `of`, dành cho dữ liệu đã được nguồn tin cậy bảo đảm. Nó không biến raw distance hoặc raw cosine thành normalized similarity.

Ở ranh giới nhận giá trị từ client hoặc một nguồn chưa được kiểm tra, nên xác thực rõ tính hữu hạn, miền giá trị và hàm được phép dùng. Không dùng `raw` để né lỗi validation.

### 5.4. Chuẩn hóa không đồng nghĩa xác suất

Một similarity `0.9` không tự có nghĩa “90% khả năng tài liệu trả lời đúng”. Đây là giá trị trên một thang tương đồng, không phải xác suất đã được hiệu chuẩn.

Hai hệ thống cùng trả `[0, 1]` có thể dùng mô hình embedding, phép biến đổi và phân phối dữ liệu khác nhau. Cùng định dạng giúp xử lý thống nhất, nhưng không tự bảo đảm cùng một giá trị có cùng chất lượng nghiệp vụ.

## 6. Ví dụ số: cùng vector nhưng điểm có ý nghĩa khác nhau

Cho query vector `q = (1, 0)` và bốn ứng viên:

| Ứng viên | Vector | Raw cosine similarity | Euclidean distance | Dot product |
| --- | --- | --- | --- | --- |
| A | `(1, 0)` | `1.0` | `0.0` | `1.0` |
| B | `(0.8, 0.6)` | `0.8` | Khoảng `0.63246` | `0.8` |
| C | `(-1, 0)` | `-1.0` | `2.0` | `-1.0` |
| D | `(2, 0)` | `1.0` | `1.0` | `2.0` |

Các con số trong bảng là phép tính toán học minh họa, chưa qua phép biến đổi score riêng của một backend.

Ba công thức gốc:

```text
dot(q, x) = tổng của q[i] * x[i]

cosine(q, x) = dot(q, x) / (norm(q) * norm(x))

euclidean(q, x) = sqrt(tổng của (q[i] - x[i])^2)
```

Cosine yêu cầu hai vector có chuẩn khác 0 để công thức trên xác định.

Ứng viên D cho thấy sự khác biệt:

- Nó cùng hướng với query nên cosine bằng 1.
- Nó khác query về độ lớn nên Euclidean distance bằng 1.
- Độ lớn của nó làm dot product bằng 2.

Do đó, không chuyển từ metric này sang metric khác mà vẫn giữ nguyên cách hiểu ngưỡng và thứ tự.

Một ví dụ biểu diễn điểm của D:

```java
Score cosineOfD = Score.of(1.0, ScoringFunction.cosine());
Score distanceOfD = Score.of(1.0, ScoringFunction.euclidean());
Score dotProductOfD = Score.of(2.0, ScoringFunction.dotProduct());
```

### 6.1. Một công thức chuẩn hóa minh họa

Giả sử ứng dụng tự công bố một quy tắc:

```text
normalizedSimilarity = (rawCosine + 1) / 2
```

Với quy tắc riêng này:

| Raw cosine | Normalized similarity của ví dụ |
| --- | --- |
| `-1.0` | `0.0` |
| `0.0` | `0.5` |
| `0.8` | `0.9` |
| `1.0` | `1.0` |

Code adapter minh họa:

```java
static Similarity normalizeCosineForThisApi(double rawCosine) {
    if (!Double.isFinite(rawCosine)
            || rawCosine < -1.0
            || rawCosine > 1.0) {
        throw new IllegalArgumentException(
                "Raw cosine phải nằm trong [-1, 1]");
    }

    double normalized = (rawCosine + 1.0) / 2.0;
    return Similarity.of(normalized, ScoringFunction.cosine());
}
```

Tên phương thức cố tình gắn với hợp đồng của API ví dụ. Đây không phải lời khẳng định rằng Commons hoặc mọi database luôn dùng công thức đó.

Nếu backend đã trả normalized similarity, áp thêm phép biến đổi có thể làm sai ngưỡng. Nếu backend trả cosine distance thay vì cosine similarity, đầu vào cũng không còn có cùng ý nghĩa với hàm trên.

### 6.2. Ngưỡng không được giữ nguyên một cách máy móc

Theo công thức riêng của ví dụ, yêu cầu:

```text
normalizedSimilarity >= 0.8
```

tương ứng:

```text
rawCosine >= 0.6
```

Nó không tương đương `rawCosine >= 0.8`.

Tương tự, nếu một backend dùng bình phương khoảng cách L2, ngưỡng trên distance và squared distance phải được diễn giải khác nhau dù thứ tự có thể giống nhau.

Khi đổi index hoặc backend, cần xác nhận phép biến đổi trước khi mang một ngưỡng nghiệp vụ cũ sang hệ thống mới.

## 7. Range, ngưỡng và thứ tự so sánh

### 7.1. Tạo range cho raw score

```java
import org.springframework.data.domain.Range;

ScoringFunction euclidean = ScoringFunction.euclidean();

Range<Score> distanceBand = Score.between(
        Score.of(0.0, euclidean),
        Score.of(0.5, euclidean));
```

Ở API 4.0, `Score.between(...)` tạo range có hai cận bao gồm. Ví dụ diễn đạt khoảng giá trị từ `0.0` đến `0.5` cho raw distance theo hợp đồng đã chọn.

Tạo range không tự chạy tìm kiếm. Module lưu trữ phải có đường query hỗ trợ nhận và diễn giải range tương ứng.

Trong ứng dụng, hãy kiểm tra hai cận có cùng loại điểm, cùng hàm, đúng thứ tự và cùng ngữ cảnh. Không coi việc tạo được một `Range` là bằng chứng rằng hai score có thể so sánh.

### 7.2. Tạo range cho normalized similarity

```java
ScoringFunction cosine = ScoringFunction.cosine();

Range<Similarity> similarityBand =
        Similarity.between(0.8, 1.0, cosine);
```

Cận trong ví dụ cũng là cận bao gồm. Nếu backend hỗ trợ normalized threshold, adapter hoặc module phải chuyển nó sang biểu thức native đúng với hàm của query/index.

`Similarity` kế thừa `Score`, nhưng generic không có quan hệ tương đương tự động giữa `Range<Similarity>` và `Range<Score>`.

Khi một hợp đồng Java cần `Range<Score>`, có thể tạo đúng kiểu range bằng các cận là `Similarity`:

```java
Similarity minimum = Similarity.of(0.8, cosine);
Similarity maximum = Similarity.of(1.0, cosine);

Range<Score> boundsAsScore = Score.between(minimum, maximum);
```

Điều này chỉ giải quyết kiểu Java. Khả năng module hiểu những cận normalized similarity vẫn phải được kiểm tra theo API tìm kiếm của module đó.

Các factory range được thể hiện trong mã nguồn [Score](https://raw.githubusercontent.com/spring-projects/spring-data-commons/4.0.0/src/main/java/org/springframework/data/domain/Score.java) và [Similarity](https://raw.githubusercontent.com/spring-projects/spring-data-commons/4.0.0/src/main/java/org/springframework/data/domain/Similarity.java).

### 7.3. Chọn comparator có ý nghĩa

`Score` ở mốc API này không cung cấp natural ordering qua `Comparable`. Nếu sắp xếp tại ứng dụng, cần comparator và ngữ cảnh rõ ràng.

Ví dụ chỉ gồm raw Euclidean distances của cùng một lần tìm kiếm:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

List<Score> distances = new ArrayList<>(List.of(
        Score.of(0.4, ScoringFunction.euclidean()),
        Score.of(0.1, ScoringFunction.euclidean()),
        Score.of(1.2, ScoringFunction.euclidean())));

distances.sort(Comparator.comparingDouble(Score::getValue));
```

Khoảng cách gần nhất đứng trước khi sắp tăng dần.

Với normalized similarity đã được xác nhận:

```java
List<Similarity> similarities = new ArrayList<>(List.of(
        Similarity.of(0.6, ScoringFunction.cosine()),
        Similarity.of(0.9, ScoringFunction.cosine()),
        Similarity.of(0.8, ScoringFunction.cosine())));

similarities.sort(
        Comparator.comparingDouble(
                (Similarity value) -> value.getValue()).reversed());
```

Không trộn vào cùng danh sách so sánh một raw distance, một raw cosine và một normalized similarity rồi chỉ sắp theo `getValue()`.

Ngay cả khi hai giá trị cùng mô tả hàm cosine, một bên là raw score và một bên là normalized similarity vẫn có thể khác thang đo. Cần xem cả loại điểm và chính sách chuẩn hóa.

### 7.4. Top-k khác với ngưỡng

Top-k giới hạn số kết quả; ngưỡng quyết định kết quả nào đủ điều kiện. Một truy vấn lấy tối đa 10 kết quả với ngưỡng similarity tối thiểu có thể trả ít hơn 10.

Ở các hệ thống tìm kiếm gần đúng, chất lượng tập ứng viên còn phụ thuộc index và các tham số tìm kiếm. Không xem ngưỡng hoặc giới hạn số lượng là lời hứa tìm được mọi tài liệu đáp ứng điều kiện trên toàn bộ dữ liệu.

## 8. Giữ Score cùng từng kết quả tìm kiếm

Commons 4.0 có `SearchResult<T>` để giữ nội dung cùng score của chính kết quả đó.

Ví dụ nhỏ, chưa truy vấn database:

```java
package example.search;

import org.springframework.data.domain.Score;
import org.springframework.data.domain.ScoringFunction;
import org.springframework.data.domain.SearchResult;
import org.springframework.data.domain.Similarity;

public class ScoreExample {

    public static void main(String[] args) {
        ScoringFunction cosine = ScoringFunction.cosine();

        Score nativeScore = Score.of(0.8, cosine);
        Similarity normalized = Similarity.of(0.9, cosine);

        SearchResult<String> hit =
                new SearchResult<>("document-17", normalized);

        System.out.println(nativeScore.getValue());
        System.out.println(nativeScore.getFunction().getName());
        System.out.println(hit.getContent());
        System.out.println(hit.getScore().getValue());
    }
}
```

Các giá trị là dữ liệu minh họa. Code không suy ra `0.9` từ `0.8`; ứng dụng phải có một chính sách chuẩn hóa hợp lệ nếu muốn liên hệ hai giá trị đó.

Ở tag 4.0.0, constructor `SearchResult(content, Score)` giữ đối tượng score được cung cấp. Constructor nhận `double` tạo score không chỉ định hàm. Nếu đã biết hàm hoặc loại normalized similarity, truyền đối tượng tương ứng sẽ giữ được ngữ cảnh tốt hơn. Xem [SearchResult 4.0.0](https://raw.githubusercontent.com/spring-projects/spring-data-commons/4.0.0/src/main/java/org/springframework/data/domain/SearchResult.java).

Trong một luồng repository thực tế:

```text
Query vector và bộ lọc nghiệp vụ
        |
        v
Module lưu trữ chọn hoặc xác định metric
        |
        v
Backend thực thi vector search
        |
        v
Adapter đọc native score và metadata
        |
        v
Score hoặc Similarity gắn với từng SearchResult<T>
        |
        v
Service áp dụng hợp đồng nghiệp vụ và tạo response
```

Khi dùng query khai báo hoặc API riêng của module, cần biết score có được backend trả về hay không, hàm nào đã dùng và adapter có thực hiện chuẩn hóa không.

Sự có mặt của class trong Commons không tự làm một derived query bất kỳ trở thành vector search. Keyword, tham số đặc biệt, index và kiểu trả về cần tuân theo khả năng của module; xem [tổng quan vector search của Spring Data](https://docs.spring.io/spring-data/commons/reference/repositories/vector-search.html).

CRUD, derived queries truyền thống, phân trang, projection, Query by Example và auditing vẫn có vai trò riêng. Đưa thêm score vào kết quả không tự cấu hình những chức năng đó hoặc làm chúng có cùng khả năng trên mọi store.

## 9. Hợp đồng dữ liệu khi đưa score ra ngoài

Nếu response chỉ có:

```json
{
  "score": 0.9
}
```

client có thể không biết nên sắp tăng hay giảm, giá trị đã chuẩn hóa chưa hoặc ngưỡng nào có ý nghĩa.

Ứng dụng có thể dùng DTO rõ ràng hơn:

```java
public record ScoreView(
        double value,
        String representation,
        String function,
        String direction) {
}
```

Ví dụ DTO cho normalized similarity:

```java
ScoreView scoreView = new ScoreView(
        similarity.getValue(),
        "normalized-similarity",
        similarity.getFunction().getName(),
        "higher-is-better");
```

`similarity` trong đoạn này là đối tượng `Similarity` đã được adapter xác nhận đúng ngữ nghĩa.

Một response minh họa:

```json
{
  "id": "document-17",
  "title": "Repository abstraction",
  "score": {
    "value": 0.9,
    "representation": "normalized-similarity",
    "function": "COSINE",
    "direction": "higher-is-better"
  }
}
```

`COSINE` là tên của enum ở mốc phiên bản đang minh họa. Nếu tên hàm là một phần hợp đồng công khai cần ổn định lâu dài, ứng dụng có thể ánh xạ tên SDK sang tên do API quản lý.

Với raw score, chiều diễn giải nên đến từ hợp đồng adapter/backend. Không luôn đặt `higher-is-better` chỉ vì field có tên `score`.

Trong nội bộ, có thể cần giữ thêm embedding model, phiên bản index hoặc phiên bản chuẩn hóa để phục vụ đánh giá. Hai query khác ngữ cảnh không nên được trộn điểm rồi xếp hạng chỉ dựa vào cùng khoảng số.

Khi ngữ nghĩa score thay đổi, hãy xem đó là thay đổi hợp đồng dữ liệu, dù field `value` vẫn có kiểu `double`.

## 10. Dự án chưa dùng Commons 4.0

Nếu dự án còn ở Commons 3.x, có thể tạo abstraction của ứng dụng để giữ ngữ nghĩa thay vì thay score bằng một `double` không ngữ cảnh:

```java
package example.search;

public record RelevanceValue(
        double value,
        String function,
        boolean normalized,
        boolean higherIsBetter) {
}
```

Đây là kiểu của ứng dụng, không phải một bản cài đặt thay thế đặt vào package của Spring Data.

Adapter của từng backend chịu trách nhiệm:

1. Đọc điểm theo API mà module hiện tại hỗ trợ.
2. Xác định đó là distance, similarity hay giá trị đã biến đổi.
3. Kiểm tra tính hợp lệ theo hợp đồng.
4. Giữ thông tin cần thiết trong kiểu nội bộ hoặc response DTO.

Khi nâng nền tảng sang dòng có API mới, có thể ánh xạ abstraction cũ sang `Score` hoặc `Similarity` tại biên adapter. Không đổi tên kiểu rồi giả định ngữ nghĩa cũng đã được chuyển đổi.

Một kế hoạch nâng cấp cần kiểm tra đồng thời Commons, module lưu trữ, driver, backend và index. Có API `Score` mới không chứng minh query hoặc cấu hình index cũ đã được nâng cấp tương thích.

## 11. Thực hành xác minh ngữ nghĩa

### 11.1. Quan sát các trường hợp cơ bản

| Thao tác hoặc tình huống | Điều cần xác minh |
| --- | --- |
| `Score.of(0.8)` | Hàm là unspecified; không tự chọn metric |
| `Score.of(-0.2, cosine)` | Raw score có thể mang giá trị âm theo metric phù hợp |
| `Similarity.of(0.0, cosine)` và `of(1.0, cosine)` | Hai biên của normalized similarity |
| `Similarity.of(-0.01, cosine)` | Factory thông thường từ chối giá trị ngoài miền |
| `Similarity.of(1.01, cosine)` | Không được coi là normalized similarity hợp lệ |
| Giá trị `NaN` hoặc vô hạn ở biên ứng dụng | Policy số hữu hạn được thực thi |
| `Similarity.raw(...)` | Hiểu rõ bước validation bị bỏ qua; không dùng như normalization |
| Range có cận dưới lớn hơn cận trên | Ứng dụng phải có chính sách validation rõ |
| Điểm dùng hàm khác nhau | Không được xếp hạng chung khi chưa có quy tắc so sánh |

Trong phép kiểm tra giá trị tính toán, dùng sai số phù hợp với số thực thay vì phụ thuộc vào so sánh chuỗi hoặc đòi mọi phép tính dấu phẩy động bằng tuyệt đối.

### 11.2. Kiểm tra cùng module và backend thực tế

Với một truy vấn tìm kiếm đã hoạt động, cần xác nhận:

- Metric của index hoặc query trùng với ngữ cảnh adapter công bố.
- Điểm trả về là raw score hay normalized similarity.
- Ngưỡng được dịch theo đúng chiều và đúng công thức.
- Thứ tự kết quả theo độ liên quan đúng với hợp đồng.
- Bộ lọc tenant và điều kiện nghiệp vụ không bị bỏ khi tìm theo vector.
- Phiên bản embedding model và số chiều vector phù hợp với index.
- DTO kết quả vẫn giữ đúng nội dung và score tương ứng.

Một phép kiểm tra chỉ tạo `Score.of(...)` trong bộ nhớ không chứng minh backend hỗ trợ metric hoặc thực thi ngưỡng đúng.

Không chọn một ngưỡng như `0.8` chỉ vì nó trông quen thuộc. Cần đánh giá trên dữ liệu đại diện và giữ lại ngữ cảnh để biết khi nào ngưỡng cần hiệu chỉnh lại.

## 12. Lỗi thường gặp

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không import được các kiểu trong bài | Commons thực tế chưa đến mốc 4.0 hoặc dùng sai package | Kiểm tra dependency được resolve và API đúng phiên bản |
| Cho rằng tạo ScoringFunction sẽ tính điểm | Nhầm mô tả metric với engine tính toán | Dùng backend hoặc thuật toán tính toán phù hợp |
| Kết quả xa hơn lại đứng trước | Sắp sai chiều của raw distance | Xác định ngữ nghĩa native score trước khi chọn comparator |
| Similarity từ chối raw cosine âm | Đưa giá trị chưa chuẩn hóa vào factory normalized | Áp dụng phép biến đổi đúng hợp đồng hoặc giữ raw Score |
| Dùng raw để bỏ lỗi validation | Nhầm factory tin cậy với bước chuyển thang điểm | Kiểm tra nguồn và ngữ nghĩa, không bỏ validation để ép dữ liệu |
| Đổi metric nhưng giữ nguyên ngưỡng | Thang đo và chiều diễn giải đã thay đổi | Hiệu chỉnh và kiểm tra threshold theo metric mới |
| Ghép điểm từ nhiều model rồi sort | Cùng miền số nhưng chưa được hiệu chuẩn chung | Giữ ngữ cảnh và thiết kế quy tắc kết hợp rõ ràng |
| Thấy constant nhưng backend từ chối | Commons mô tả được hàm mà module/index chưa hỗ trợ | Kiểm tra khả năng thực tế của module và backend |
| Client hiểu 0.9 là xác suất 90% | Hợp đồng response thiếu ngữ nghĩa | Công bố representation và ý nghĩa nghiệp vụ rõ |
| API mới biên dịch nhưng query không chạy | Mới cập nhật value type, chưa có tích hợp vector search phù hợp | Kiểm tra toàn bộ nền tảng, adapter và index |

Khi sử dụng một điểm tìm kiếm, hãy xác định phiên bản API, hàm chấm điểm, loại giá trị, chiều “tốt hơn” và nơi thực hiện chuẩn hóa. Những thông tin đó giúp `Score`, `Similarity` và `ScoringFunction` phục vụ đúng vai trò dùng chung mà vẫn tôn trọng khả năng của từng kho dữ liệu.
