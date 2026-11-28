# Đọc API đúng phiên bản thay vì giả định mọi evaluator giống nhau

## 1. Vì sao phải bắt đầu từ phiên bản đang dùng?

Một lập trình viên muốn đánh giá câu trả lời của ứng dụng Spring AI bằng `RelevancyEvaluator` và `FactCheckingEvaluator`. Họ tìm một ví dụ trên mạng, sao chép đoạn code rồi gặp lỗi biên dịch:

```text
required: List<Document>
found:    List<Content>
```

Khi sửa được lỗi kiểu dữ liệu, họ lại gặp lỗi khi gọi constructor của `FactCheckingEvaluator`. Cuối cùng ứng dụng chạy được, nhưng dashboard lại cho rằng mọi câu trả lời đều trượt vì `getScore()` bằng `0` ở một evaluator vốn chỉ cung cấp phán quyết boolean.

Đây là ba vấn đề **khác nhau**:

1. **Chữ ký API** có thể khác ví dụ tài liệu cũ.
2. **Cách khởi tạo và hành vi** thay đổi theo implementation và release.
3. **Ý nghĩa đầu ra** không được định nghĩa đồng nhất cho mọi evaluator chỉ vì chúng triển khai cùng một interface.

Bài này thuộc chương **API Evaluator** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Toàn module hướng tới đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking, kiểm thử RAG hoặc gọi công cụ; đồng thời dùng metrics, traces, token, chi phí và độ trễ để tìm nguyên nhân suy giảm chất lượng theo phiên bản prompt, model và pipeline.

**Mục tiêu sau bài học:** biết xác định đúng phiên bản Spring AI đang chạy, tìm Javadoc và mã nguồn tương ứng, xác minh chữ ký từng evaluator, phân biệt API với chi tiết triển khai, chọn ví dụ có thể biên dịch, và thiết kế kiểm thử hồi quy khi nâng cấp thư viện.

> **Phạm vi:** các ví dụ trong bài dùng Spring AI 2.1.0 làm mốc minh họa. Không suy ra từ đó rằng mọi bản 1.x, 2.0.x, 2.1.x hoặc snapshot có cùng chữ ký. Khi áp dụng, luôn đối chiếu với artifact thật sự của dự án.

## 2. Năm lớp thông tin cần phân biệt

Trong hệ sinh thái Spring AI, một tên class có thể xuất hiện ở nhiều nơi, nhưng các nơi ấy không có cùng mức độ ràng buộc đối với mã nguồn dự án.

| Nguồn thông tin | Trả lời câu hỏi | Giới hạn |
|---|---|---|
| **Dependency đã được resolve** | Ứng dụng biên dịch/chạy với JAR nào? | Cần biết cả phiên bản transitives, không chỉ khai báo trực tiếp |
| **Javadoc theo phiên bản** | Class, constructor, method, kiểu tham số và mức truy cập công khai là gì? | Thường không mô tả đầy đủ parser, rubric, retry, score |
| **Mã nguồn theo release tag/commit** | Implementation thực sự tính pass/score và gọi judge thế nào? | Không dùng mã ở `main` để kết luận về một JAR release cũ |
| **Reference documentation theo nhánh** | Chức năng giải quyết bài toán gì và cách dùng được khuyến nghị ra sao? | Có thể có đoạn minh họa chưa cập nhật, thiếu import hoặc khác Javadoc |
| **Release notes / migration guide** | Có thay đổi gì khi nâng cấp và phải sửa gì? | Không thay thế việc kiểm tra runtime và chạy test |

Mức độ ưu tiên khi giải quyết một lỗi **biên dịch**:

```text
1. Phiên bản artifact đã được resolve
2. Javadoc / class bytecode tương ứng với artifact ấy
3. Mã nguồn của đúng release tag
4. Hướng dẫn migration và reference của cùng nhánh
5. Bài viết, ví dụ hoặc snippet tìm thấy ở nơi khác
```

Khi tìm hiểu **ý nghĩa pass/score**, cần xem thêm implementation và test của đúng release, bởi interface chỉ mô tả kiểu dữ liệu.

### 2.1. “current”, “latest”, “main” và “snapshot” không phải số phiên bản cố định

- `/docs/current/api/...` có thể trỏ tới một phiên bản khác theo thời gian. Kết quả search cache và trang truy cập trực tiếp đôi khi phản ánh các thời điểm cập nhật khác nhau; hãy **đọc tiêu đề có version** trên Javadoc.
- `/reference/...` thường thể hiện một nhánh tài liệu đang được duy trì, không phải cam kết mã của mọi release.
- `/reference/2.1-SNAPSHOT/...` hoặc Javadoc snapshot có thể thay đổi ngay khi chưa có release chính thức.
- `github.com/spring-projects/spring-ai/tree/main` là mã đang phát triển, không phải artifact mà bạn đã build tuần trước.
- Git tag `v2.1.0` là điểm tham chiếu cố định cho mã nguồn release 2.1.0; tag/commit phải được đối chiếu với artifact tương ứng.

Ngày **20/11/2026**, Spring AI công bố bản **2.1.0 GA**. Việc bản này đã ra mắt không có nghĩa dự án của bạn tự động chuyển sang 2.1.0. Nếu BOM vẫn ở 2.0.3 hoặc 1.1.x, phải đọc API của nhánh đó.

## 3. Bước 1 — Xác định dependency nào thực sự được dùng

Đừng đoán phiên bản từ đoạn code vừa tìm được, từ tên folder bài học hoặc từ phiên bản Spring Boot. Lấy thông tin từ cấu hình build và **dependency graph đã resolve**.

### 3.1. Spring AI BOM trên Maven

Ví dụ minh họa khai báo Spring AI 2.1.0 bằng Maven:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.ai</groupId>
            <artifactId>spring-ai-bom</artifactId>
            <version>2.1.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là phần cấu hình cần đặt trong `pom.xml` của ứng dụng Maven (không phải một POM đầy đủ). BOM giúp quản lý bộ phiên bản Spring AI nhất quán; ứng dụng vẫn cần dependency/starter thật sự cho model, evaluation và các thành phần sử dụng.

Có thể kiểm tra artifact Spring AI đã được resolve bằng lệnh:

```bash
mvn dependency:tree -Dincludes=org.springframework.ai
```

Đối chiếu các artifact có mặt trên **compile classpath** và **runtime classpath**. Ví dụ, một dependency transitively kéo thành phần `spring-ai-client-chat` từ nhánh khác có thể gây `NoSuchMethodError` hoặc `NoClassDefFoundError` khi chạy.

### 3.2. Spring AI BOM trên Gradle

```groovy
dependencies {
    implementation platform("org.springframework.ai:spring-ai-bom:2.1.0")
    implementation "org.springframework.ai:spring-ai-starter-model-openai"
}
```

Tên starter ở đây chỉ là ví dụ khi dùng OpenAI làm nhà cung cấp model; cần chọn đúng starter/provider và cách quản lý dependency theo phiên bản thực tế.

Lệnh **tham khảo để người học chạy trong dự án của mình**:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-ai-client-chat --configuration runtimeClasspath
```

Trên Windows có thể dùng `gradlew.bat` thay cho `./gradlew`. Nếu dùng compile classpath để biên dịch nhưng runtime classpath chứa phiên bản khác, cần kiểm tra cả hai. Nếu dự án dùng version catalog hoặc dependency constraints, kiểm tra nơi các phiên bản được đưa vào graph.

**Mấu chốt:** số phiên bản trong dòng khai báo không luôn là phiên bản cuối cùng sau dependency resolution. Nếu phát hiện nhiều phiên bản không nhất quán, sửa cấu hình dependency trước khi thay code evaluator.

### 3.3. Đừng suy luận tương thích từ số major của Spring Boot

Spring AI 2.1.0 được công bố cùng nền Spring Boot 4.2. Tuy nhiên, không nên lấy thông tin đó để suy ra mọi project Spring Boot 4.2 đều đang dùng Spring AI 2.1.0 hoặc mọi artifact AI nhánh 2.1 đều tương thích với mọi bản Boot cũ. Đọc bảng tương thích trong release/upgrade notes và BOM được chọn.

Khi cần ghi một kết quả đánh giá có thể tái lập, lưu tối thiểu:

```text
springAiBomVersion
resolvedEvaluationArtifactVersion
springBootVersion
javaVersion
generationModelId
judgeModelId
promptVersion
judgeRubricVersion
retrievalPipelineVersion
```

Các trường trên thuộc **manifest của lần chạy hoặc báo cáo**, không tự xuất hiện trong `EvaluationResponse`.

## 4. Bước 2 — Tra đúng Javadoc trước khi viết code

Javadoc là nơi kiểm tra **chữ ký public/protected**, constructor, builder method, getter và kiểu trả về.

Với bài toán evaluator, bắt đầu từ package:

- `org.springframework.ai.evaluation`: `Evaluator`, `EvaluationRequest`, `EvaluationResponse`.
- `org.springframework.ai.chat.evaluation`: `RelevancyEvaluator`, `FactCheckingEvaluator`.

Trình tự tra Javadoc:

1. Mở index Javadoc dành cho **phiên bản của dependency**.
2. Tìm đúng package và class.
3. Đọc **Constructor Summary** và **Method Summary**, chú ý `public`, `protected`, `static`, parameter types và return types.
4. Xem overload, annotation như `@Nullable` hoặc API deprecated nếu có.
5. Đọc Javadoc của builder class lồng nhau, không chỉ class ngoài.
6. Nếu method không có trong bản đó, đừng giả định thư viện sẽ tự chuyển từ API ở `main` hoặc bản snapshot sang.

Ví dụ một URL có version rõ ràng:

```text
https://docs.spring.io/spring-ai/docs/2.1.0/api/
```

Cần kiểm tra đường dẫn và tiêu đề phiên bản khi mở từng trang. Với bản đang dùng không có Javadoc công khai dễ truy cập, có thể tra mã nguồn chính xác theo tag hoặc JAR source gắn với artifact đã resolve.

### 4.1. Ví dụ thực tế: `List<Content>` và `List<Document>`

Một đoạn mã trong trang *Evaluation Testing* từng mô tả:

```java
private final List<Content> dataList;
```

Trong khi Javadoc của các phiên bản mới được tra tại thời điểm biên soạn nêu constructor:

```java
EvaluationRequest(
    String userText,
    List<Document> dataList,
    String responseContent
)
```

Điều này là dấu hiệu **tài liệu minh họa và API được xuất bản có thể không đồng bộ**.

Nếu dependency thật đòi `List<Document>`, cách gọi phù hợp là:

```java
import java.util.List;

import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;

EvaluationRequest request = new EvaluationRequest(
    "Thời hạn hoàn tiền?",
    List.of(new Document(
        "Khách hàng được yêu cầu hoàn tiền trong 30 ngày."
    )),
    "Thời hạn hoàn tiền là 30 ngày."
);
```

Không “chữa” bằng raw types, cast không an toàn hoặc tắt cảnh báo compiler. Sửa đúng kiểu theo **Javadoc của artifact mà bạn đã resolve**.

Nếu một bài viết cũ dùng `Content`, không đủ bằng chứng để kết luận API toàn bộ các bản Spring AI đều từng dùng `Content`. Nó có thể đơn giản là tài liệu chưa cập nhật.

## 5. Bước 3 — Đọc hợp đồng chung, sau đó đọc từng implementation

Tất cả evaluator bên dưới đều thực hiện hợp đồng kiểu:

```java
EvaluationResponse evaluate(EvaluationRequest request);
```

Nhưng cùng implement `Evaluator` **không có nghĩa** các class:

- Dùng cùng constructor hoặc builder.
- Đọc cùng trường của `EvaluationRequest`.
- Dùng cùng prompt judge và parser.
- Trả score trên cùng thang đo.
- Cung cấp feedback hoặc metadata có cùng schema.
- Gọi provider với cùng số lượt, timeout hoặc model.
- Cho phép dùng cùng threshold quality gate.

Bảng định hướng khi xem mã nguồn:

| Điều phải tra ở từng class | Câu hỏi khi đọc |
|---|---|
| **Construction** | Tạo bằng constructor public, static factory hay builder? |
| **Input mapping** | Dùng `userText`, `dataList`, `responseContent` theo ý nghĩa nào? |
| **Prompt** | Mẫu prompt có tham số gì, có cho phép thay thế không? |
| **Judge I/O** | Cần output `YES/NO`, JSON, score hay cấu trúc khác? |
| **Parser** | Thế nào là verdict hợp lệ? Xử lý null/chuỗi lạ ra sao? |
| **Response** | `pass`, `score`, `feedback`, `metadata` được tạo thế nào? |
| **Exceptions** | Lỗi gọi model/parse được ném hay chuyển thành verdict? |
| **Tests** | Bộ test của chính release có chốt lại hành vi nào? |

Không nên viết wrapper chung dựa vào một evaluator rồi ép các evaluator khác phải tuân theo hành vi ấy.

## 6. RelevancyEvaluator: đối chiếu constructor, builder và cách parse

`RelevancyEvaluator` kiểm tra câu trả lời có phù hợp câu hỏi và ngữ cảnh không. Trong các triển khai được xem xét quanh Spring AI 2.x, nó xây prompt dùng ba phần:

```text
query   ← EvaluationRequest.userText
context ← dữ liệu Document hỗ trợ
response← EvaluationRequest.responseContent
```

Prompt mặc định hướng judge trả `YES` hoặc `NO`. Trong mã nguồn được đối chiếu, câu trả lời được trim/strip và so sánh toàn chuỗi với `yes` (không phân biệt chữ hoa/thường); khi khớp, response mang `pass=true`, `score=1`, còn lại `pass=false`, `score=0`.

Đây là **mô tả của một implementation cụ thể**, không phải luật bắt buộc của interface `Evaluator`. Khi đổi release, kiểm tra lại mã nguồn/tag và test parser.

### 6.1. Mẫu khởi tạo được Javadoc công bố

Cách dùng public constructor trong các nhánh API tương ứng:

```java
RelevancyEvaluator evaluator = new RelevancyEvaluator(
    ChatClient.builder(judgeModel)
);
```

Nếu muốn dùng builder để cấu hình prompt, **đọc Builder Javadoc của bản đang dùng**. Ở nhánh source có builder, cách dùng là:

```java
RelevancyEvaluator evaluator = RelevancyEvaluator.builder()
    .chatClientBuilder(ChatClient.builder(judgeModel))
    .promptTemplate(relevancePrompt)
    .build();
```

Đoạn thứ hai là ví dụ trong phạm vi đã có `judgeModel` và `relevancePrompt`, với import tương ứng. Nó chỉ đúng nếu builder của release cung cấp các phương thức này. Không tự đổi sang một cú pháp `new RelevancyEvaluator(..., prompt)` nếu constructor đó không public.

### 6.2. Khi sao chép custom prompt

Nếu builder cho phép thay prompt, phải giữ các placeholder mà evaluator nội bộ truyền khi render. Với RelevancyEvaluator theo tài liệu ở nhánh tương ứng, các placeholder gồm:

```text
{query}
{response}
{context}
```

Nếu custom prompt dùng tên biến khác, có thể gặp lỗi khi render, hoặc judge bị thiếu thông tin. Đồng thời phải giữ hợp đồng output parser: prompt yêu cầu JSON dài trong khi parser chỉ nhận `YES/NO` sẽ tạo kết quả sai lệch.

Trước khi triển khai custom prompt, xem cả **TemplateRenderer** và cách implementation render template của chính release.

## 7. FactCheckingEvaluator: không giả định constructor giống RelevancyEvaluator

`FactCheckingEvaluator` chấm xem một claim/câu trả lời có được document làm căn cứ hỗ trợ không. Về ý nghĩa, nó khác relevance: một câu có vẻ đúng chủ đề vẫn có thể mâu thuẫn số liệu trong tài liệu.

Trong một số tài liệu cũ, bạn có thể gặp cú pháp:

```java
new FactCheckingEvaluator(ChatClient.builder(judgeModel))
```

Tuy nhiên, Javadoc của nhánh Spring AI 2.1 có mô tả **constructor được bảo vệ (protected)** nhận `ChatClient.Builder` và tham số prompt, đồng thời cung cấp static factory/builder.

Ví dụ cách dùng API builder trong nhánh ấy:

```java
FactCheckingEvaluator evaluator = FactCheckingEvaluator
    .builder(ChatClient.builder(judgeModel))
    .build();
```

Và phương thức riêng cho một judge chuyên kiểm chứng có thể là:

```java
FactCheckingEvaluator minicheck = FactCheckingEvaluator
    .forBespokeMinicheck(ChatClient.builder(minicheckModel));
```

Ở đây `judgeModel` và `minicheckModel` đã được cấu hình từ provider; **không thay model tùy ý** nếu cách prompt/output dành riêng cho một loại judge.

**Kết luận khi tra API:** nếu constructor bạn muốn gọi không public, không thử ép quyền truy cập hoặc sửa package. Hãy tìm builder/static factory được công bố trong **đúng Javadoc của version**. Không tự suy rằng mọi evaluator có `builder()` không đối số giống nhau: `FactCheckingEvaluator.builder(ChatClient.Builder)` và `RelevancyEvaluator.builder()` là hai chữ ký khác nhau ở những phiên bản tương ứng.

### 7.1. Cùng trả EvaluationResponse nhưng thang score có thể khác

`FactCheckingEvaluator` được dùng để xác nhận một claim có được chứng cứ hỗ trợ không. Trong một số nhánh implementation, nó tạo `EvaluationResponse` bằng constructor không truyền tham số `score` riêng. Khi đó `getScore()` có thể có giá trị mặc định nhưng **không phải điểm tin cậy có thể so sánh**.

Ngược lại, một RelevancyEvaluator có parser nhị phân có thể đặt score `1` nếu pass và `0` nếu fail.

Không viết:

```java
// Không an toàn giữa những evaluator có semantics khác nhau.
boolean factuallyCorrect = factualityResult.getScore() >= 0.5f;
```

Với báo cáo pass rate, đọc `factualityResult.isPass()`. Nếu muốn đo score theo thang `[0,1]` liên tục, chọn hoặc xây evaluator/rubric **công bố rõ thang, chiều tối ưu và threshold**.

## 8. EvaluationResponse: constructor, score và metadata cần được hiểu theo bản cụ thể

Chữ ký Javadoc của `EvaluationResponse` trong các nhánh đã tra có hai constructor:

```java
new EvaluationResponse(
    boolean pass, float score,
    String feedback, Map<String, Object> metadata
);

new EvaluationResponse(
    boolean pass,
    String feedback, Map<String, Object> metadata
);
```

Đây là các **chữ ký minh họa**, không phải câu lệnh Java biên dịch trực tiếp.

| Thành phần | Do API đảm bảo? | Phải kiểm tra implementation/rubric? |
|---|---|---|
| Có getter `isPass()` | Có ở bản Javadoc được tra | Tiêu chí nào quyết định pass |
| Có getter `getScore()` | Có ở bản Javadoc được tra | Score nhị phân, liên tục hay không được cấp ý nghĩa |
| Có getter `getFeedback()` | Có | Có dữ liệu giải thích thực sự hay chuỗi rỗng |
| Có getter `getMetadata()` | Có | Những khóa nào xuất hiện và có ổn định không |
| Điểm `0.8` là “đúng 80%” | Không | Chỉ khi được hiệu chỉnh thành xác suất với bằng chứng |
| Mọi evaluator dùng ngưỡng `0.5` | Không | Threshold do từng rubric/ứng dụng quy định |

Ví dụ evaluator tự viết có thể trả:

```java
import java.util.Map;
import org.springframework.ai.evaluation.EvaluationResponse;

EvaluationResponse response = new EvaluationResponse(
    true,
    0.75f,
    "Đã đáp ứng 3 trong 4 điều kiện tùy chọn.",
    Map.of(
        "criterion", "optional-fields",
        "rubricVersion", "v1",
        "matched", 3,
        "total", 4,
        "minimumRequired", 3
    )
);
```

Score `0.75` ở đây là **tỷ lệ 3/4 điều kiện thỏa mãn**, không phải xác suất câu trả lời đúng 75%. Các khóa metadata là quy ước ứng dụng.

### 8.1. Đừng đánh đồng lỗi thực thi với quality fail

Nếu `evaluate(...)` ném exception vì judge timeout, caller có thể **không nhận được** `EvaluationResponse`. Nếu judge trả `NO` hợp lệ, caller nhận response với `isPass()==false`.

Một lớp báo cáo nên tách:

```text
EVALUATED_PASS  — Đã có verdict và tiêu chí đạt.
EVALUATED_FAIL  — Đã có verdict và tiêu chí không đạt.
EVALUATION_ERROR— Lỗi gọi judge hoặc không có verdict đáng tin.
INVALID_INPUT   — Thiếu dữ liệu cần thiết theo rubric.
INVALID_OUTPUT  — Raw judge output không khớp schema, nếu phát hiện.
```

Đây là trạng thái **do ứng dụng đặt ra**, không phải enum của Spring AI. Nếu evaluator nội bộ chuyển mọi raw output ngoài `YES` thành `false`, chỉ từ `isPass()==false` không thể phân biệt verdict `NO` với output sai định dạng. Muốn phát hiện, cần kiểm soát parser/adapter hoặc trace raw judge output an toàn.

## 9. Ví dụ hoàn chỉnh: gọi hai evaluator theo API được xác minh

Giả sử ứng dụng có `ChatModel` dành cho judge và một câu trả lời RAG đã được lưu. Mẫu sau dùng cách khởi tạo phù hợp với những chữ ký đã nêu cho nhánh Spring AI 2.1:

```java
import java.util.List;
import java.util.Map;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.FactCheckingEvaluator;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;

public final class VersionAwareEvaluationExample {

    public record Verdicts(
        EvaluationResponse relevance,
        EvaluationResponse factuality
    ) {}

    public static Verdicts evaluate(ChatModel judgeModel) {
        String question = "Thời hạn hoàn tiền là bao lâu?";

        List<Document> context = List.of(
            new Document(
                "refund-policy-v3",
                "Có thể yêu cầu hoàn tiền trong 30 ngày từ khi nhận hàng.",
                Map.of("source", "policies/refund", "version", "v3")
            )
        );

        String answer =
            "Thời hạn yêu cầu hoàn tiền là 30 ngày từ khi nhận hàng.";

        EvaluationRequest request = new EvaluationRequest(
            question, context, answer
        );

        var relevance = new RelevancyEvaluator(
            ChatClient.builder(judgeModel)
        );

        var factuality = FactCheckingEvaluator
            .builder(ChatClient.builder(judgeModel))
            .build();

        return new Verdicts(
            relevance.evaluate(request),
            factuality.evaluate(request)
        );
    }
}
```

**Lưu ý cách sử dụng:**

- Code cần các dependency Spring AI 2.1 tương ứng và một provider `ChatModel` đã được cấu hình; không tự chạy được nếu chưa có judge model.
- Dùng hai `ChatClient.Builder` riêng để mỗi evaluator có cấu hình độc lập.
- Dữ liệu `Document` là chứng cứ minh họa; với RAG thật, cần lấy đúng context của lượt sinh câu trả lời.
- Không suy ra `isPass()==true` cho mọi model judge; kết quả còn phụ thuộc prompt, dữ liệu, parser và model.
- Đọc `isPass()` riêng cho từng criterion; đừng trung bình các `getScore()` nếu chưa xác nhận semantics.

Với dự án ở phiên bản khác, hãy sửa **cách khởi tạo** theo Javadoc tương ứng, rồi biên dịch/test. Không tự dùng đoạn code này làm bằng chứng rằng một phiên bản Spring AI bất kỳ đều hỗ trợ mọi phương thức trên.

## 10. Bước 4 — Đọc source và test của đúng release

Khi Javadoc cho biết chữ ký nhưng không giải thích tại sao `score` bằng 0 hoặc parser xử lý `YES.` thành fail, hãy đọc source.

### 10.1. Chọn đúng Git tag hoặc commit

Trên GitHub Spring AI, mở phần **Releases/Tags** và chọn release tương ứng, ví dụ `v2.1.0`. Sau đó tìm mã nguồn của class trong module chat evaluation.

Không đọc source từ:

```text
.../blob/main/.../FactCheckingEvaluator.java
```

rồi tuyên bố đó là logic của JAR `2.1.0`. `main` có thể đã chứa thay đổi sau ngày phát hành.

Cần đối chiếu các điểm:

1. Constructor, builder, static factory và mức truy cập.
2. `evaluate(...)` map `EvaluationRequest` sang prompt như thế nào.
3. Prompt/template dùng placeholder gì.
4. Parser nhận những giá trị judge nào.
5. `EvaluationResponse` được tạo bằng constructor có score hay không.
6. Các ngoại lệ có được truyền tiếp, wrapped hay chuyển thành response.
7. Unit/integration tests đi kèm khẳng định những hành vi nào.

### 10.2. Mã nguồn và Javadoc trả lời hai loại câu hỏi khác nhau

Ví dụ, Javadoc có thể xác nhận `getScore()` trả về kiểu `float`. Nhưng muốn biết `FactCheckingEvaluator` **có gán score theo kết luận hay không**, phải xem `evaluate(...)` của **đúng artifact/release**.

Ngược lại, nếu muốn biết constructor nào **được phép gọi từ mã ứng dụng**, nhìn source chưa đủ: một constructor có mặt trong source nhưng được đánh dấu `protected` sẽ không được gọi từ code bên ngoài package như constructor public. Javadoc cho biết mức truy cập, và compiler là bước kiểm chứng thực tế.

## 11. Bước 5 — Dùng compiler và test làm kiểm chứng cuối

Không cần đưa ngay toàn bộ ứng dụng RAG vào bài test. Nên xác nhận theo ba tầng:

| Tầng | Kiểm tra | Ví dụ lỗi phát hiện |
|---|---|---|
| **Compile smoke test** | Import, constructor, builder, getter, generics | `List<Content>` sai, factory không tồn tại, constructor không public |
| **Unit test deterministic** | Quy tắc `pass`/`score` của evaluator tự viết | Sai threshold hoặc metadata contract |
| **Integration test judge** | Prompt, parser, kết nối model, raw output | Judge trả chuỗi sai schema, timeout, quota |
| **RAG integration test** | Retrieval → context → generation → evaluator | Source sai, document bị cắt, hallucination |
| **Dataset regression** | Pass rate và false pass/fail trên nhiều case có nhãn | Hành vi judge/pipeline thay đổi sau nâng cấp |

### 11.1. Ví dụ compile smoke test cho hai cách tạo evaluator

Ví dụ JUnit kiểm tra rằng **chữ ký** được sử dụng có thể gọi được trong phiên bản của dự án:

```java
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.FactCheckingEvaluator;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.chat.model.ChatModel;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.mock;

class EvaluatorApiSmokeTest {

    @Test
    void createsEvaluators() {
        ChatModel judgeModel = mock(ChatModel.class);

        var relevance = new RelevancyEvaluator(
            ChatClient.builder(judgeModel)
        );

        var factuality = FactCheckingEvaluator
            .builder(ChatClient.builder(judgeModel))
            .build();

        assertNotNull(relevance);
        assertNotNull(factuality);
    }
}
```

**Điều kiện chạy:** ví dụ cần JUnit 5 và Mockito trong test classpath (thường có qua starter kiểm thử của Spring Boot). Mock `ChatModel` chỉ giúp tạo builder để kiểm tra chữ ký và cách khởi tạo; không gọi `evaluate(...)` vì mock chưa được cấu hình để trả nội dung từ model.

Trong dự án Spring Boot có `ChatModel` bean, một mẫu `@SpringBootTest` hoặc cấu hình test tương ứng có thể cấp dependency. Khi test có gọi `evaluate(...)` thật, cần xem đó là integration test có chi phí/độ trễ.

### 11.2. Test hành vi, không chỉ kiểm tra class tồn tại

Một class compile được chưa đủ để tin vào cách chấm:

- `RelevancyEvaluator` có thể yêu cầu chính xác `YES/NO`; model mới có thể trả thêm giải thích.
- `FactCheckingEvaluator` có thể dùng prompt/formatter khác hoặc bản dành riêng cho Minicheck.
- Khi thêm custom prompt, tên placeholder và parser có thể không còn tương thích.
- Model judge khác nhau có thể cho verdict khác nhau ngay cả với cùng input.
- Provider có thể hết quota/timeout; tình huống này không chứng minh câu trả lời ứng dụng sai.

Cần có tập mẫu gồm câu đúng, câu sai, phủ định, số liệu sai, thiếu context, nguồn mâu thuẫn và trường hợp judge trả output không hợp lệ. Nếu bản nâng cấp đổi parser, nên chạy những case này trước khi so sánh pass rate theo ứng dụng.

## 12. Quy trình nâng cấp Spring AI có thể tái lập

Khi muốn nâng từ một release cũ sang 2.1.0 (hoặc release khác), thực hiện theo các bước sau:

1. **Chụp baseline:** lưu dependency graph, BOM version, prompt/model/index/judge version, dataset và kết quả đánh giá hiện tại.
2. **Đọc release/upgrade notes:** liệt kê API đã thay đổi, class deprecated, migration yêu cầu và tương thích Spring Boot/JDK.
3. **Chọn artifact đích:** cập nhật BOM và các dependency cần thiết theo một phiên bản nhất quán.
4. **Đọc Javadoc đúng version:** kiểm tra các kiểu và constructor đang dùng trong project.
5. **So sánh source/tag:** chú ý `evaluate(...)`, prompt, parser, cách tính `pass/score` và xử lý lỗi.
6. **Sửa code theo compiler:** dùng overload/builder hợp lệ, tránh raw casts hoặc gọi constructor không public.
7. **Chạy kiểm thử theo tầng:** compile → deterministic tests → judge integration → RAG/tool integration → dataset regression.
8. **So sánh có kiểm soát:** chỉ kết luận model/prompt ứng dụng tốt hơn nếu các biến khác và rubric/judge đã được cố định hoặc được ghi rõ.

### 12.1. Tại sao phải khóa judge khi đánh giá regression?

Giả sử prompt sinh không thay đổi, nhưng sau khi nâng Spring AI, parser của evaluator lại diễn giải output judge khác đi. Pass rate có thể thay đổi dù tất cả câu trả lời của ứng dụng vẫn như cũ.

Để tách nguồn biến động, lưu bộ `EvaluationRequest` hoặc câu trả lời cố định từ trước nâng cấp và chấm lại bằng judge cũ/mới. Nếu kết quả khác nhau trên cùng input, thay đổi có thể đến từ **judge, parser, rubric hoặc cách chuyển dữ liệu**. Sau khi xác minh bộ chấm, mới đánh giá độ thay đổi của generation/retrieval.

## 13. Case study: sửa một ví dụ cũ theo API đã resolve

Giả sử bạn có snippet sau trong một bài viết cũ:

```java
// Ví dụ rút gọn, có thể không compile trên version đang dùng.
List<Content> docs = loadContext();
EvaluationRequest request =
    new EvaluationRequest(question, docs, answer);

FactCheckingEvaluator fact =
    new FactCheckingEvaluator(ChatClient.builder(judgeModel));
```

Trên một dependency Spring AI mà Javadoc nêu `List<Document>` và chỉ công bố constructor `FactCheckingEvaluator` dạng protected, compiler có thể báo lỗi.

**Bước sửa thứ nhất — xác nhận JAR:** kiểm tra dependency graph xem evaluator và request thực sự thuộc bản nào.

**Bước sửa thứ hai — thay kiểu context theo API của bản đó:**

```java
import java.util.List;

import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;

List<Document> documents = List.of(
    new Document("Chính sách hoàn tiền: 30 ngày kể từ khi nhận hàng.")
);

EvaluationRequest request =
    new EvaluationRequest(question, documents, answer);
```

**Bước sửa thứ ba — đổi cách tạo fact checking theo Javadoc đúng bản:**

```java
FactCheckingEvaluator fact = FactCheckingEvaluator
    .builder(ChatClient.builder(judgeModel))
    .build();
```

**Bước sửa thứ tư — kiểm tra hành vi:** build, chấm một ca đúng và một ca sai, đọc `isPass()`; kiểm tra source trước khi diễn giải `getScore()`.

**Bước sửa thứ năm — tránh sửa nhầm:** không thay `RelevancyEvaluator` bằng `FactCheckingEvaluator` chỉ vì cả hai là `Evaluator`. Relevance và grounded factuality đo hai điều khác nhau.

Bài học từ case study là phải sửa **theo compiler và version contract**, không tự đoán “nếu constructor A thay đổi thì constructor B chắc cũng thay đổi”.

## 14. RAG: đúng evaluator chưa đủ nếu context không đúng lần chạy

Bản thân API chuẩn có thể được gọi chính xác nhưng phép đánh giá vẫn sai nếu `EvaluationRequest` lấy nhầm context.

Với `RetrievalAugmentationAdvisor`, tài liệu Spring AI mô tả cách lấy context từ metadata của `ChatResponse` bằng khóa `RetrievalAugmentationAdvisor.DOCUMENT_CONTEXT`. Cần đối chiếu advisor/version vì không phải pipeline nào cũng cung cấp cùng metadata.

Các nhóm dữ liệu khác nhau:

| Nhóm | Dùng để làm gì? |
|---|---|
| Query gốc `userText` | Chấm câu trả lời có đúng ý định người dùng |
| Rewritten search query | Chẩn đoán retrieval, có thể khác query gốc |
| Retrieved candidates | Đánh giá retrieval trước filtering/rerank |
| Final generation context | Chấm answer theo nguồn model thực sự thấy |
| Gold documents / expected answer | Đo correctness hoặc recall@k theo nhãn chuẩn |
| `responseContent` | Nội dung câu trả lời thật của lượt đang kiểm tra |

Với nhiều vòng retrieval hoặc tool call, cần lưu mỗi bước và version của dữ liệu. `EvaluationRequest` không có trường tích hợp cho toàn bộ tool-call timeline; muốn chấm **tool selection/arguments** phải lấy thêm traces hoặc event logs.

Khi nâng phiên bản advisor/vector store, so sánh output và context snapshot theo `runId` để xác định một regression đến từ retrieval, generation hay đánh giá.

## 15. Observability và khả năng tái hiện

Một evaluator cũng là phần mềm phụ thuộc API và model nên cần quan sát:

| Tín hiệu | Mục đích |
|---|---|
| Quality verdict theo criterion | Theo dõi relevance/factuality pass rate |
| Judge output validity | Biết parser/model judge có trả schema đúng |
| Evaluation errors/retries | Phân biệt lỗi hạ tầng với quality fail |
| Judge latency và token usage | Tính chi phí/độ trễ của việc chấm |
| Generation latency và token usage | Tính chi phí/độ trễ phục vụ ứng dụng |
| Retrieval/tool spans | Tìm nguồn sai hoặc lời gọi công cụ sai |
| Version manifest | Xác định BOM, judge, prompt, model, pipeline, dataset |

**Không nhầm `EvaluationResponse.getScore()` với latency, chi phí hoặc token usage.** Score thuộc rubric, còn vận hành thuộc telemetry của model/provider và những span ứng dụng ghi.

### 15.1. Ví dụ bản ghi báo cáo có phiên bản

```json
{
  "caseId": "refund-030",
  "runId": "eval-run-2026-11-27",
  "criterion": "factual-support",
  "springAiBomVersion": "2.1.0",
  "evaluatorImplementation": "FactCheckingEvaluator",
  "generationModel": "generation-model-id",
  "judgeModel": "judge-model-id",
  "judgeRubricVersion": "fact-v2",
  "retrievalIndexVersion": "refund-index-v3",
  "promptVersion": "prompt-v8",
  "status": "EVALUATED_PASS",
  "pass": true,
  "scoreSemantics": "implementation-specific",
  "traceId": "trace-example-001"
}
```

Đây là **schema tự thiết kế**, không phải JSON của `EvaluationResponse`. Tên model mang tính placeholder và không biểu thị một model có thật được sử dụng. Nếu evaluator không có score định lượng hữu ích, đừng tự đưa giá trị mặc định vào `normalizedScore` như một điểm chất lượng.

Không dùng `caseId`, raw `userText` hoặc toàn bộ feedback làm **metric label**: cardinality và nguy cơ rò rỉ dữ liệu quá lớn. Lưu chi tiết ở report/log/trace phù hợp, giới hạn quyền truy cập và loại bỏ thông tin nhạy cảm.

## 16. Bảng lỗi phổ biến khi đọc API sai phiên bản

| Sai lầm | Triệu chứng | Cách sửa |
|---|---|---|
| Chỉ đọc trang Reference cũ | Ví dụ dùng kiểu dữ liệu không khớp Javadoc | Kiểm tra signature trên JAR/Javadoc theo version |
| Xem `/current` là cố định | Tài liệu thay đổi mà code không đổi | Ghi version rõ, kiểm tra title |
| Đọc source `main` cho release cũ | Học nhầm builder/parser mới | Chọn release tag hoặc commit tương ứng |
| Chỉ đổi BOM mà không kiểm tra resolved graph | Mixed dependencies hoặc linkage error | Kiểm tra compile/runtime classpath |
| Coi mọi evaluator có cùng constructor | Constructor không public, static factory khác chữ ký | Đọc riêng Constructor Summary và Builder |
| Dùng `List<Content>` khi API cần `List<Document>` | Compilation error | Tạo đúng `Document` theo API |
| Coi mọi `score` đều là xác suất | Dashboard/threshold vô nghĩa | Tìm scale, parser, rubric từ implementation |
| Tự phân loại `score=0` là fail | Mất các phán quyết pass hợp lệ | Đọc `isPass()`, kiểm tra semantics score |
| Dùng prompt trả JSON nhưng parser chỉ nhận YES/NO | False negatives hoặc output invalid | Kiểm tra parser, output schema và test |
| Đồng nhất lỗi judge với lỗi model sinh | Chẩn đoán sai regression | Phân tách evaluation error khỏi quality fail |
| Trộn context của hai run | Judge chấm sai chứng cứ | Giữ runId/context snapshot |
| Bỏ qua version judge/rubric | Pass rate đổi nhưng không giải thích được | Version hóa bộ chấm và cố định dataset |

## 17. Thực hành kiểm tra phiên bản và hành vi

### Bài tập 1 — Tìm đúng signature

Dự án báo `required: List<Document>`, nhưng snippet dùng `List<Content>`. Hãy mô tả thứ tự xử lý.

**Gợi ý:** kiểm tra dependency đã resolve, mở `EvaluationRequest` Javadoc theo version, xác nhận constructor, chuyển dữ liệu về `List<Document>` và biên dịch. Không dùng raw cast.

### Bài tập 2 — Constructor không public

Javadoc nêu `protected FactCheckingEvaluator(ChatClient.Builder, String)` và `static builder(ChatClient.Builder)`. Làm sao tạo evaluator từ code ứng dụng?

**Gợi ý:** dùng builder public với `ChatClient.builder(judgeModel)`, sau đó `build()`. Không gọi trực tiếp constructor protected từ package bên ngoài.

### Bài tập 3 — Phán quyết và score

Một evaluator cho `isPass()==true`, `getScore()==0`. Dashboard cho rằng chất lượng bằng 0%. Kết luận có đúng không?

**Đáp án:** không có cơ sở. Phải xem cách tạo score và mục đích rubric của evaluator; một implementation có thể không cấp score hữu ích. Với pass rate, đếm `isPass()`.

### Bài tập 4 — Khác nhau giữa bản Release và Snapshot

Bạn đọc code ở nhánh `main` và thấy `builder()` không đối số, nhưng dự án trên release cũ không compile. Làm sao xử lý?

**Gợi ý:** tìm source/Javadoc của đúng tag release đang dùng, xác nhận factory method được public và dùng cú pháp phù hợp. Không sửa build sang snapshot chỉ để phù hợp snippet nếu không có chủ đích nâng cấp.

### Bài tập 5 — Regression do judge

Sau khi nâng Spring AI, câu trả lời từ ứng dụng giữ nguyên nhưng relevance pass rate giảm. Một số judge trả “YES, because ...”.

**Gợi ý:** kiểm tra parser và prompt của evaluator ở hai release, chấm lại một tập câu trả lời cố định, kiểm tra raw judge output có kiểm soát. Không khẳng định model sinh bị giảm chất lượng khi chưa tách biến số.

### Bài tập 6 — Context không đúng lượt

Một integration test chạy RAG với vector store mới nhưng đưa tài liệu chuẩn từ một fixture bên ngoài vào `EvaluationRequest`. Test pass. Có chứng minh retrieval đang tốt không?

**Đáp án:** không. Cần kiểm tra retrieved documents thực tế và so với gold document IDs; nếu muốn chấm groundedness theo context model đã thấy thì phải đưa đúng generation context của lượt chạy.

## 18. Quy trình kiểm tra nhanh trước khi dùng một đoạn code Spring AI

- [ ] Đã biết phiên bản BOM và artifact evaluation thực tế được resolve?
- [ ] Đã chọn Javadoc cùng phiên bản, đọc đúng tên package và class?
- [ ] Đã phân biệt `public/protected`, constructor và static factory?
- [ ] Đã kiểm tra overload, generic type và nullable contract?
- [ ] Đã đọc Builder Javadoc thay vì đoán method của các evaluator giống nhau?
- [ ] Đã xem source/test theo release tag khi cần hiểu prompt, parser, score?
- [ ] Đã xác nhận `EvaluationRequest` chứa đúng query/context/answer?
- [ ] Đã tách `isPass()`, `getScore()` và lỗi gọi judge theo implementation?
- [ ] Đã compile trước khi chạy model thật, rồi kiểm tra bằng ca có nhãn?
- [ ] Đã lưu prompt/model/judge/index/version khi so sánh regression?
- [ ] Đã tách metrics/traces và chi phí judge khỏi serving?
- [ ] Đã bảo vệ context, prompt và log khỏi lộ dữ liệu nhạy cảm?

## 19. Tài liệu tham khảo

1. [Spring AI 2.1.0 GA — thông báo phát hành ngày 20/11/2026](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/): phiên bản và thông tin nền Spring Boot 4.2.
2. [Spring AI — Release/Upgrade notes](https://github.com/spring-projects/spring-ai/releases): chọn phiên bản đã khóa và xem các thay đổi.
3. [Spring AI Documentation — các Javadoc theo version](https://docs.spring.io/spring-ai/docs/): chọn thư mục `2.1.0/`, `2.0.3/` hoặc đúng phiên bản đang dùng.
4. [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): hợp đồng evaluator, cách đánh giá relevance/fact checking và ví dụ RAG; luôn đối chiếu Javadoc khi sao chép.
5. [Spring AI 2.1 — FactCheckingEvaluator Javadoc](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/evaluation/FactCheckingEvaluator.html): builder/factory và các phương thức công khai của nhánh.
6. [Spring AI — EvaluationRequest Javadoc](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/evaluation/EvaluationRequest.html): ví dụ chữ ký constructor; kiểm tra lại version hiện trên trang.
7. [Spring AI — GitHub Source Releases](https://github.com/spring-projects/spring-ai/tags): tra mã nguồn theo tag cố định, không đồng nhất `main` với bản phát hành.
8. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): metrics, traces và thông tin cần liên kết với kết quả đánh giá.

*Chữ ký và hành vi ở bài học được dùng để minh họa quy trình đọc API theo phiên bản. API thực tế trong dự án phụ thuộc artifact đã resolve; sau mỗi lần nâng cấp phải xác minh Javadoc, source tag và kiểm thử tương ứng trước khi kết luận một implementation vẫn có hành vi cũ.*
