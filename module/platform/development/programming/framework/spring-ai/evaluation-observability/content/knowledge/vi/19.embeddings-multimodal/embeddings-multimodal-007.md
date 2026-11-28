# Kiểm tra dữ liệu thiếu và khác biệt giữa các nhà cung cấp

## 1. Vì sao một response thành công vẫn có thể thiếu dữ liệu quan trọng?

Một ứng dụng Spring AI có thể đổi provider để tối ưu chất lượng, chi phí hoặc độ trễ. Mã gọi vẫn dùng shared interface như ChatModel, EmbeddingModel hay TranscriptionModel, nhưng response metadata và telemetry có thể khác nhau:

- Provider A trả input tokens, output tokens và response model.
- Provider B chỉ trả total tokens, không tách input/output.
- Provider C không trả usage trong response, nhưng có API billing riêng.
- Provider D trả kết quả thành công nhưng không có response ID.
- Một adapter có built-in observation; adapter khác chỉ có HTTP metrics hoặc chưa có GenAI observation.
- Một model hỗ trợ streaming, model khác chỉ hỗ trợ call đồng bộ.

Nếu dashboard coi trường không xuất hiện là số 0, nhóm vận hành có thể kết luận sai rằng provider B không tiêu thụ token. Nếu adapter tự điền model ID mặc định khi response không có, báo cáo có thể gán nhầm model. Nếu ứng dụng chuyển provider nhưng giữ nguyên cách tính chi phí, estimate có thể lệch hóa đơn.

Bài **“Kiểm tra dữ liệu thiếu và khác biệt giữa các nhà cung cấp”** thuộc chương **Embedding và đa phương thức** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module hướng đến đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; đồng thời theo dõi metrics, traces, chi phí và độ trễ để phát hiện suy giảm qua từng phiên bản prompt, model và pipeline.

**Mục tiêu:** nhận diện dữ liệu thiếu đúng nguyên nhân, so sánh provider theo capability và semantics, chuẩn hóa dữ liệu nhưng vẫn giữ nguồn gốc, thiết kế fallback có kiểm soát và kiểm thử để việc đổi provider không làm dashboard hoặc cost ledger sai lệch.

## 2. “Thiếu dữ liệu” có nhiều ý nghĩa khác nhau

Một trường không có giá trị không phải lúc nào cũng là lỗi. Cần phân loại trước khi quyết định retry, cảnh báo hoặc tính toán.

| Trạng thái | Ý nghĩa | Ví dụ | Cách xử lý |
| --- | --- | --- | --- |
| **REPORTED** | Nguồn đã trả giá trị | Provider báo 1.200 input tokens | Lưu giá trị và nguồn |
| **REPORTED_ZERO** | Nguồn xác nhận giá trị bằng 0 | Provider trả usage = 0 theo hợp đồng | Lưu 0, giữ bằng chứng |
| **NOT_REPORTED** | Provider không gửi trường đó | Response không có token usage | Giữ unknown, không tự điền 0 |
| **NOT_SUPPORTED** | API/model không hỗ trợ capability hoặc field | Model không có streaming | Đánh dấu capability |
| **NOT_REQUESTED** | Ứng dụng không yêu cầu thông tin/chức năng | Không yêu cầu response format cụ thể | Không xem là lỗi provider |
| **NOT_APPLICABLE** | Trường không có ý nghĩa cho operation | Image size ở một thao tác transcription | Không tạo cảnh báo thiếu |
| **REDACTED** | Có dữ liệu nhưng chính sách không cho lưu/xuất | Transcript bị ẩn khỏi trace | Giữ trạng thái redacted |
| **EMPTY** | Có trường nhưng nội dung rỗng | Transcript là chuỗi rỗng | Xử lý theo validation nghiệp vụ |
| **ERROR** | Không lấy được dữ liệu do lỗi | Timeout khi gọi usage endpoint | Ghi lỗi và retry theo policy |
| **PENDING** | Dữ liệu chưa sẵn sàng | Billing report được tổng hợp sau | Đợi đối soát |
| **STALE** | Giá trị cũ, không còn phù hợp thời điểm hiện tại | Capability cache chưa refresh | Làm mới theo TTL/version |

**Phân biệt ba trường hợp dễ nhầm:**

- **NOT_REPORTED:** provider có thể hỗ trợ nhưng request này không có dữ liệu.
- **NOT_SUPPORTED:** không thể kỳ vọng trường đó từ implementation/model hiện tại.
- **REDACTED:** dữ liệu có thể tồn tại nhưng hệ thống chủ động không xuất vì bảo mật.

Nếu một metric usage thiếu, trước hết cần biết đây là provider không báo usage, instrumentation không thu được metadata, exporter chưa scrape hay request chưa hoàn tất. Mỗi nguyên nhân cần cách xử lý khác nhau.

### Không dùng null và 0 thay thế cho nhau

```text
reportedInputTokens = 0
    -> provider xác nhận không có input token theo hợp đồng.

reportedInputTokens = null
availability = NOT_REPORTED
    -> không có dữ liệu để kết luận.

reportedInputTokens = null
availability = REDACTED
    -> dữ liệu không được lưu/xuất theo chính sách.
```

Một dashboard có thể hiển thị số 0 cho biểu đồ để dễ đọc, nhưng tầng lưu trữ và tính toán phải giữ trạng thái gốc. **Giá trị hiển thị không được làm mất ý nghĩa dữ liệu.**

## 3. Khác biệt giữa provider không chỉ nằm ở tên model

Khi chuyển từ provider A sang provider B, cần so sánh nhiều lớp:

| Lớp | Khác biệt có thể gặp | Câu hỏi cần xác minh |
| --- | --- | --- |
| **Capability** | Có chat, embedding, image, transcription hay TTS? | Model/adapter có thật sự hỗ trợ operation này? |
| **Input modality** | Text, image, audio, video, PDF hoặc kết hợp | Định dạng nào được nhận? Có giới hạn kích thước? |
| **Options** | Temperature, dimensions, voice, size, response format | Tùy chọn có được hỗ trợ hay bị bỏ qua? |
| **Output semantics** | Text, vector, URL, Base64, byte stream | Kiểu dữ liệu và số lượng kết quả là gì? |
| **Usage metadata** | Input/output/total tokens, image units, audio duration | Field nào được trả và đơn vị nào? |
| **Streaming** | Có stream hay chỉ call; chunk semantics khác nhau | Chunk đầu tiên và completion được xác định thế nào? |
| **Errors** | HTTP status, exception, safety refusal, quota | Có phân biệt lỗi tạm thời và lỗi request không? |
| **Limits** | Context, batch size, file size, rate limit | Giới hạn nào được provider công bố? |
| **Observability** | Built-in observation, HTTP span, app timer | Metric/span nào thực sự được phát? |
| **Billing** | Token, ảnh, thời lượng, ký tự, request hoặc tier | Hóa đơn dùng đơn vị và rounding nào? |

Cùng implement một interface không có nghĩa các tính năng phụ giống nhau. Tài liệu Spring AI mô tả abstraction chung để giảm phụ thuộc provider, đồng thời mỗi integration vẫn cung cấp options riêng của provider. Tính portable nằm ở **hợp đồng chung**, còn capability và option cụ thể vẫn phải được kiểm tra.

## 4. Ví dụ khác biệt theo phạm vi observability của Spring AI 2.1.0

Tài liệu Observability Spring AI 2.1.0 liệt kê phạm vi built-in model observation theo từng loại model:

| Model interface | Provider được tài liệu 2.1.0 liệt kê có observability |
| --- | --- |
| EmbeddingModel | Mistral AI, Ollama, OpenAI |
| ImageModel | OpenAI, Stability AI |
| TextToSpeechModel | OpenAI, ElevenLabs, Google GenAI |
| TranscriptionModel | OpenAI, Google GenAI |

Đây là danh sách **instrumentation của Spring AI**, không phải danh sách tất cả provider có API tương ứng.

Ví dụ rõ nhất là audio: tài liệu TTS API 2.1.0 liệt kê OpenAI, ElevenLabs, Google GenAI và Qxotic jinfer; nhưng bảng observability TTS chỉ liệt kê OpenAI, ElevenLabs và Google GenAI. Tài liệu Transcription API cũng có implementation Qxotic jinfer trong khi bảng observability transcription không liệt kê provider đó.

Điều này cho thấy ba khẳng định phải được kiểm chứng độc lập:

1. **Provider có API/implementation** cho operation.
2. **Spring AI adapter có built-in observation** cho implementation đó.
3. **Telemetry có xuất tới registry/backend** trong cấu hình thực tế.

Nếu provider chưa được liệt kê ở danh sách built-in observation, model vẫn có thể chạy. Khi cần theo dõi, ứng dụng có thể bổ sung Timer/Observation ở boundary, đồng thời ghi rõ đó là **application-level telemetry**.

### Không đóng băng ma trận provider trong mã nguồn

Bảng trên có phiên bản và có thể thay đổi khi Spring AI thêm adapter hoặc instrumentation. Nên lưu ma trận capability theo release, kiểm tra tài liệu đúng BOM và xác nhận bằng integration test. Không dùng một bảng provider viết từ snapshot làm bằng chứng cho ứng dụng đang chạy stable version khác.

## 5. Portable interface và provider-specific options

Các abstraction phổ biến:

| Model type | Shared interface | Công việc |
| --- | --- | --- |
| Chat | ChatModel / ChatClient | Tạo phản hồi |
| Embedding | EmbeddingModel | Tạo vector |
| Image | ImageModel | Sinh ảnh |
| Transcription | TranscriptionModel | Chuyển audio thành text |
| Text-to-Speech | TextToSpeechModel | Chuyển text thành audio |

Ví dụ service có thể phụ thuộc vào shared interface:

```java
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.stereotype.Service;

@Service
public class SearchEmbeddingService {

    private final EmbeddingModel embeddingModel;

    public SearchEmbeddingService(EmbeddingModel embeddingModel) {
        this.embeddingModel = embeddingModel;
    }

    public float[] embedQuery(String query) {
        if (query == null || query.isBlank()) {
            throw new IllegalArgumentException("Query rỗng");
        }
        return embeddingModel.embed(query);
    }
}
```

Service không cần biết model cụ thể là OpenAI hay Mistral để gọi phương thức chung. Nhưng khi cần tùy chọn riêng như task type, dimensions hoặc option chỉ provider hỗ trợ, application phải dùng đúng options class/contract tương ứng.

**Không ép mọi option thành một field chung rồi bỏ qua khác biệt.** Nếu một provider không hỗ trợ dimensions, việc adapter âm thầm bỏ qua option có thể khiến index schema và output vector không tương thích.

### Quy tắc khi chuẩn hóa option

- Field chung: chuẩn hóa nếu semantics thực sự tương đương.
- Field riêng provider: giữ trong phần provider-specific config.
- Field không hỗ trợ: trả capability status rõ ràng.
- Field bị bỏ qua: ghi nhận IGNORED_BY_ADAPTER nếu điều đó có thể xảy ra.
- Field có default: lưu effective value khi cần tái hiện request, không chỉ lưu giá trị người dùng gửi.

## 6. Phân biệt capability, configuration và observed behavior

Một provider có thể công bố hỗ trợ streaming, nhưng model cụ thể hoặc deployment hiện tại có thể không bật. Cấu hình stream=true cũng chưa chứng minh đã nhận nhiều chunk.

Nên giữ ba lớp:

| Lớp | Ví dụ | Nguồn |
| --- | --- | --- |
| **Declared capability** | Provider docs nói model hỗ trợ streaming | Tài liệu/model catalog |
| **Configured capability** | Ứng dụng bật streaming và chọn model cụ thể | Runtime configuration |
| **Observed behavior** | Request thật trả về nhiều chunk và completion event | Integration test/runtime telemetry |

Tương tự, model có thể hỗ trợ image input nhưng một deployment cụ thể bị giới hạn định dạng. Capability ở cấp provider không đảm bảo tất cả model, region hoặc account đều giống nhau.

Một cấu trúc capability profile:

```json
{
  "provider": "provider-a",
  "model": "model-vision-v3",
  "apiVersion": "2026-10",
  "springAiVersion": "2.1.0",
  "operation": "chat",
  "capabilities": {
    "textInput": "SUPPORTED",
    "imageInput": "SUPPORTED",
    "audioInput": "NOT_SUPPORTED",
    "streaming": "SUPPORTED",
    "toolCalling": "SUPPORTED",
    "usageBreakdown": "PARTIAL"
  },
  "verifiedAt": "2026-11-27T10:00:00Z",
  "verificationSource": "integration-test"
}
```

Đây là schema ứng dụng tự thiết kế. Trạng thái SUPPORTED trong profile nên gắn với model, API version, region và cấu hình có liên quan, không chỉ provider name.

## 7. Thiết kế schema usage chuẩn hóa mà không làm mất đơn vị

Một schema nội bộ tốt cần chứa:

- modality: text, image, audio, video hoặc embedding;
- operation: chat, image_generation, transcription, text_to_speech, embedding;
- unit: token, image, audio_second, character, byte hoặc đơn vị cụ thể;
- quantity: giá trị số nếu có;
- availability: trạng thái dữ liệu;
- source: provider_reported, application_measured, estimated, billing_export;
- provider, model, apiVersion, springAiVersion;
- requestId, attempt, observedAt;
- billingBasis, priceVersion, currency nếu tính chi phí.

Ví dụ response usage một phần:

```json
{
  "provider": "provider-a",
  "model": "text-model-v3",
  "operation": "chat",
  "modality": "text",
  "usage": {
    "inputTokens": {
      "value": 1200,
      "unit": "token",
      "availability": "REPORTED",
      "source": "provider_reported"
    },
    "outputTokens": {
      "value": null,
      "unit": "token",
      "availability": "NOT_REPORTED",
      "source": "provider_response"
    },
    "totalTokens": {
      "value": 1200,
      "unit": "token",
      "availability": "REPORTED",
      "source": "provider_reported"
    }
  }
}
```

Ở ví dụ này không được suy outputTokens = 0 chỉ vì provider không tách output. Nếu total bao gồm input và output theo hợp đồng, ta có thể tính output là 0 **chỉ khi** biết rõ total và input cùng semantics, không có cached/reasoning token hoặc loại token khác bị loại trừ. Nếu chưa xác nhận, giữ NOT_REPORTED.

### Giữ raw metadata bên cạnh normalized fields

Không nên chỉ lưu một object normalized rồi bỏ toàn bộ metadata gốc. Một adapter mới có thể cần field trước đó chưa được schema nội bộ biết đến. Mẫu tốt:

- **Normalized view:** các field chung đã hiểu và có đơn vị rõ.
- **Raw provider metadata:** dữ liệu gốc có chọn lọc, được kiểm soát quyền truy cập và retention.
- **Normalization version:** phiên bản logic chuyển đổi.
- **Unknown fields:** giữ trong vùng mở rộng có giới hạn, không tự đưa mọi field vào metric.

Không lưu API key, prompt nhạy cảm, transcript hoặc binary image/audio chỉ vì muốn giữ raw payload. Có thể giữ response ID, model ID, usage metadata và hash cần thiết nếu chính sách dữ liệu cho phép.

## 8. Java: biểu diễn giá trị có trạng thái thay vì số nullable

Một kiểu dữ liệu nội bộ có thể như sau:

```java
import java.math.BigDecimal;

public enum DataAvailability {
    REPORTED,
    REPORTED_ZERO,
    NOT_REPORTED,
    NOT_SUPPORTED,
    NOT_REQUESTED,
    NOT_APPLICABLE,
    REDACTED,
    EMPTY,
    ERROR,
    PENDING,
    STALE
}

public record MeasuredValue(
        BigDecimal value,
        String unit,
        DataAvailability availability,
        String source) {

    public MeasuredValue {
        if (unit == null || unit.isBlank()) {
            throw new IllegalArgumentException("Thiếu unit");
        }
        if (availability == null) {
            throw new IllegalArgumentException("Thiếu availability");
        }
        if ((availability == DataAvailability.REPORTED
                || availability == DataAvailability.REPORTED_ZERO)
                && value == null) {
            throw new IllegalArgumentException(
                    "Trạng thái reported phải có value");
        }
        if (availability == DataAvailability.REPORTED_ZERO
                && value != null && value.signum() != 0) {
            throw new IllegalArgumentException(
                    "REPORTED_ZERO phải có value bằng 0");
        }
        if (value != null && value.signum() < 0) {
            throw new IllegalArgumentException("Giá trị âm không hợp lệ");
        }
    }

    public static MeasuredValue notReported(String unit, String source) {
        return new MeasuredValue(
                null, unit, DataAvailability.NOT_REPORTED, source);
    }

    public static MeasuredValue reportedZero(String unit, String source) {
        return new MeasuredValue(
                BigDecimal.ZERO, unit,
                DataAvailability.REPORTED_ZERO, source);
    }
}
```

Đây là kiểu dữ liệu ứng dụng đề xuất, không phải lớp Spring AI. Với một số đại lượng có thể âm (ví dụ score có miền từ -1 tới 1), validation cần theo domain cụ thể thay vì áp quy tắc không âm chung. Ví dụ này dành cho usage quantity và các bộ đếm.

Một MeasuredValue giúp code downstream không phải đoán null có nghĩa gì. Khi tính cost, chỉ chấp nhận trạng thái có dữ liệu phù hợp; NOT_REPORTED, REDACTED hoặc ERROR không thể tự chuyển thành số 0.

Khi đưa ví dụ vào dự án Java, tách DataAvailability và MeasuredValue thành các file public top-level riêng; code block ghép chúng để minh họa mối quan hệ giữa enum và record.

## 9. Chuẩn hóa usage: phải biết semantics trước khi đổi tên field

Giả sử provider A trả prompt_tokens và completion_tokens; provider B trả inputTokenCount và outputTokenCount; provider C chỉ trả totalTokenCount.

Không chỉ đổi tên key. Cần biết:

- token nào đã bao gồm cached input;
- reasoning tokens có nằm trong output hay tách riêng;
- total có phải tổng input + output không;
- usage có bao gồm tool call hay không;
- dữ liệu là token model báo, tokenizer ước lượng hay số billing;
- usage ở cấp request, batch, session hay từng item.

Một mapping an toàn có thể:

| Provider field | Internal field | Điều kiện |
| --- | --- | --- |
| prompt_tokens | input_tokens | Provider định nghĩa prompt tokens là input của request |
| completion_tokens | output_tokens | Provider định nghĩa completion tokens là output |
| total_tokens | total_tokens | Lưu đúng total, không cộng lại component |
| inputTokenCount | input_tokens | Đã xác minh semantics và unit |
| totalTokenCount | total_tokens | Không tự suy output nếu thiếu thông tin |

Nếu chỉ có total, normalized view phải ghi input_tokens = NOT_REPORTED, output_tokens = NOT_REPORTED, total_tokens = REPORTED. Không chia tổng theo tỷ lệ ước lượng rồi ghi như provider data.

### Ví dụ adapter mapping

```java
import java.math.BigDecimal;
import java.util.Map;

public final class UsageNormalizer {

    private UsageNormalizer() {
    }

    public static MeasuredValue readNumeric(
            Map<String, ?> metadata,
            String providerKey,
            String unit) {

        if (metadata == null || !metadata.containsKey(providerKey)) {
            return MeasuredValue.notReported(
                    unit, "provider_response");
        }

        Object raw = metadata.get(providerKey);
        if (!(raw instanceof Number number)) {
            return new MeasuredValue(
                    null, unit, DataAvailability.ERROR,
                    "invalid_provider_value");
        }

        BigDecimal value;
        try {
            value = new BigDecimal(number.toString());
        }
        catch (NumberFormatException ex) {
            return new MeasuredValue(
                    null, unit, DataAvailability.ERROR,
                    "invalid_provider_value");
        }
        if (value.signum() < 0) {
            return new MeasuredValue(
                    null, unit, DataAvailability.ERROR,
                    "negative_provider_value");
        }
        if (value.signum() == 0) {
            return MeasuredValue.reportedZero(
                    unit, "provider_reported");
        }

        return new MeasuredValue(
                value, unit, DataAvailability.REPORTED,
                "provider_reported");
    }
}
```

Ví dụ chỉ áp dụng cho metadata dạng số và field đã được xác minh. Không đưa nguyên JSON provider bất kỳ vào method này rồi giả định mọi key cùng đơn vị. Một adapter thật cần mapping theo provider, API version và operation; field không biết phải giữ là unknown hoặc bỏ qua có log phù hợp, không đoán.

## 10. Khác biệt giữa modality: không chuẩn hóa mọi thứ thành token

| Modality | Đơn vị volume có thể đo | Usage provider có thể trả | Billing basis có thể gặp |
| --- | --- | --- | --- |
| Text/chat | Ký tự, input/output tokens | Input, output, total, cached, reasoning | USD/1M tokens, tier |
| Embedding | Số input text, tokens, vector count, dimensions | Input tokens hoặc usage riêng | USD/1M tokens, request |
| Image input | Số ảnh, pixel, byte, resolution tier | Image tokens hoặc image units | USD/ảnh, token, resolution tier |
| Image generation | Số ảnh yêu cầu/trả, size, quality | Token/usage nếu provider hỗ trợ | USD/ảnh, quality tier, request |
| STT | Audio seconds, bytes, sample rate | Audio tokens hoặc duration | USD/phút, giây, token |
| TTS | Text chars/tokens, output audio seconds/bytes | Text/audio tokens nếu có | USD/ký tự, token, phút |
| Video | Số frame, duration, resolution | Video/image/audio tokens nếu provider báo | Token, duration hoặc đơn vị riêng |

Các đơn vị trong bảng là **những khả năng thường gặp**, không khẳng định mọi provider có đủ các field. Ví dụ một provider có thể tính ảnh theo image token nội bộ nhưng không expose image token trong response. Khi đó application không được tự chế một giá trị provider-reported.

### Cần giữ input và output riêng

- input_audio_seconds khác output_audio_seconds.
- input_images khác generated_images.
- input_tokens khác output_tokens.
- requested_images khác returned_images và persisted_images.

Không cộng các số khác đơn vị vào một metric usage_total. Chỉ tổng hợp sau khi quy đổi theo **billing rule đã xác minh**, hoặc tổng hợp chi phí tiền tệ cùng currency.

## 11. Khác biệt ở embedding: dimension và usage là hai loại dữ liệu

Với EmbeddingModel, các provider có thể khác nhau ở:

- model name, deployment alias và version;
- vector dimension và khả năng yêu cầu dimensions;
- task type hoặc chế độ document/query;
- normalization, vector precision và output ordering;
- usage metadata có hay không;
- built-in observation có hay không.

Trong Spring AI 2.1.0, observability reference liệt kê built-in EmbeddingModel observation cho Mistral AI, Ollama và OpenAI. Tài liệu mô tả gen_ai.client.operation để đo thời gian method call, cùng gen_ai.client.token.usage khi có usage; dimension và usage là các trace attributes theo bảng high-cardinality.

**Dimension không phải token count.** Một vector 1.024 chiều không có nghĩa input dùng 1.024 tokens. Nếu provider không trả dimensions trong trace, có thể đo trực tiếp float[].length ở application boundary. Nếu provider không trả usage, giữ NOT_REPORTED.

Khi đổi provider/model, phải kiểm cả dimension và embedding space. Hai model cùng 768 chiều không có bảo đảm vector tương thích ngữ nghĩa.

## 12. Khác biệt ở image và audio: output metadata không đồng nhất

### ImageModel

Một ImageResponse có thể chứa nhiều generation; ảnh có thể được trả dưới dạng URL hoặc Base64. Provider khác nhau ở options, format, size, style, số ảnh và metadata usage. Không được mặc định:

- một model call = một ảnh;
- URL luôn bền vững;
- Base64 có nghĩa file đã hợp lệ;
- mọi response đều có token usage;
- requested image count bằng returned/persisted image count.

Tài liệu observability Spring AI 2.1.0 liệt kê OpenAI và Stability AI cho built-in ImageModel observation. Provider khác có API ImageModel không đồng nghĩa đã có cùng built-in observation.

### Transcription và TTS

STT và TTS có output khác nhau: transcription trả text, TTS trả audio bytes hoặc stream. Provider có thể khác nhau về language options, codec, voice, timestamps, speaker labels, chunking và usage.

Tài liệu Spring AI 2.1.0 liệt kê OpenAI và Google GenAI cho transcription observations; OpenAI, ElevenLabs và Google GenAI cho TTS observations. Dữ liệu audio và transcript không được export mặc định do có thể nhạy cảm. Không đọc lại Resource chỉ để đo metrics nếu stream có thể chỉ đọc một lần.

### Không ép response vào một schema làm mất ý nghĩa

Có thể có một envelope chung cho request, status và trace, nhưng payload riêng theo modality cần giữ semantics của nó. Không ép TTS bytes, image URL và embedding vector vào cùng một trường result rồi để downstream tự đoán loại dữ liệu.

## 13. Missingness trong observability: metric không xuất hiện có nhiều nguyên nhân

Giả sử dashboard không thấy gen_ai.client.token.usage. Các giả thuyết:

1. Provider không trả usage cho operation/model đó.
2. Adapter chưa ánh xạ usage metadata vào observation.
3. Provider/adapter chưa có built-in observation cho loại model.
4. Request chưa hoàn thành hoặc bị hủy.
5. Registry/exporter không nhận hoặc không xuất meter.
6. Prometheus scrape chưa chạy hoặc query lọc nhãn sai.
7. Dữ liệu bị loại theo policy hoặc sampling.

**Không kết luận provider không tiêu thụ token chỉ vì metric trống.**

Với gen_ai.client.operation, cần phân biệt built-in model observation với HTTP client observation. Một HTTP span có thể xuất hiện mà không có GenAI model span; ngược lại, model observation có thể xuất hiện mà response usage không có. Mỗi tín hiệu trả lời một câu hỏi khác nhau.

### Ma trận điều tra

| Quan sát | Khả năng | Kiểm tra tiếp |
| --- | --- | --- |
| API call thành công, không có GenAI span | Adapter chưa instrumented hoặc registry context bị mất | Version, bean, ObservationRegistry |
| Có GenAI span, không có token usage | Provider không báo usage hoặc mapping thiếu | Response metadata/provider docs |
| Có HTTP span, không có GenAI span | HTTP instrumentation hoạt động độc lập | Model-level instrumentation |
| Có token metadata trong response, không có counter | Observation handler/exporter chưa ghi | Registry, meter filter, exporter |
| Không có cả HTTP và GenAI span | Request chưa chạy hoặc tracing chưa cấu hình | Log request, sampling, exporter |
| Có metric nhưng dashboard rỗng | Query label/filter hoặc scrape issue | Raw Prometheus series |

## 14. Kiểm tra response trước khi chuẩn hóa

Một response cần được kiểm tra theo thứ tự:

1. **Operation:** response thuộc loại model nào?
2. **Provider/model identity:** provider, model/deployment và API version có xác định được không?
3. **Execution status:** thành công, lỗi, refusal, cancel hay partial?
4. **Output presence:** có output hợp lệ theo hợp đồng không?
5. **Usage:** field nào được provider báo, unit gì, cấp request hay item?
6. **Metadata completeness:** field nào thiếu, bị redacted hoặc không hỗ trợ?
7. **Provenance:** dữ liệu đến từ response, app measurement, estimate hay billing export?
8. **Timestamp:** dữ liệu thuộc request/attempt nào và có còn mới không?

Ví dụ response transcription có transcript rỗng:

- Model call có thể hoàn thành thành công ở cấp HTTP.
- transcript = EMPTY ở cấp nghiệp vụ.
- Token usage có thể NOT_REPORTED.
- Duration audio đầu vào có thể REPORTED từ decoder của ứng dụng.
- Không nên đánh dấu toàn bộ event là SUCCESS nếu business contract yêu cầu transcript không rỗng.

Tương tự, một ImageModel call có thể trả hai generation, nhưng chỉ một ảnh tải thành công. Cần trạng thái riêng cho model response và artifact persistence.

## 15. Java: kiểm tra dữ liệu thiếu theo trạng thái

Có thể viết test để ngăn code downstream coi unknown là zero:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class MeasuredValueTest {

    @Test
    void notReportedDoesNotBecomeZero() {
        MeasuredValue value = MeasuredValue.notReported(
                "token", "provider_response");

        assertNull(value.value());
        assertEquals(DataAvailability.NOT_REPORTED,
                value.availability());
    }

    @Test
    void reportedZeroIsAnExplicitMeasurement() {
        MeasuredValue value = MeasuredValue.reportedZero(
                "token", "provider_reported");

        assertEquals(BigDecimal.ZERO, value.value());
        assertEquals(DataAvailability.REPORTED_ZERO,
                value.availability());
    }

    @Test
    void reportedValueRequiresQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> new MeasuredValue(
                        null, "token", DataAvailability.REPORTED,
                        "provider_reported"));
    }
}
```

Các test trên kiểm tra **mô hình dữ liệu nội bộ**, không gọi provider. Có thể bổ sung test cho NOT_SUPPORTED, REDACTED, ERROR, PENDING và STALE, đồng thời xác nhận cost calculator chỉ nhận trạng thái hợp lệ.

Với Java, mỗi public top-level class/record/enum nên đặt trong file riêng khi đưa code vào dự án. Các đoạn trong bài ghép nhiều kiểu để giải thích quan hệ giữa chúng.

## 16. Kiểm thử khác biệt giữa provider bằng contract tests

Một contract test nên kiểm tra điều mà ứng dụng **thực sự phụ thuộc**, không cố ép mọi provider trả cùng một JSON.

Ví dụ contract chung cho embedding:

- Với một input hợp lệ, có output vector.
- Vector không rỗng và các phần tử hữu hạn.
- Dimension phù hợp profile/index.
- Nếu provider hỗ trợ response index, index không trùng và đúng phạm vi.
- Nếu provider không hỗ trợ field usage, trạng thái phải là NOT_SUPPORTED hoặc NOT_REPORTED theo đúng capability; không bịa giá trị.
- Nếu model identity không có trong response, profile cấu hình phải được lưu riêng với provenance là configured, không giả là response-reported.

Contract cho audio:

- STT trả transcript theo định dạng mà ứng dụng chấp nhận hoặc trạng thái EMPTY.
- TTS trả bytes/stream có thể kiểm tra MIME/codec.
- Streaming contract xác định subscription, chunk, complete, error và cancel.
- Usage/duration được lưu với đúng unit và nguồn.

Contract cho image:

- Kiểm số generation trả về.
- Kiểm URL/Base64 và bước tải/giải mã thực tế.
- Tách requested, returned, validated và persisted images.
- Kiểm options size/quality có được provider áp dụng hay không.

### Bảng kết quả test theo provider

| Test | Provider A | Provider B | Provider C |
| --- | --- | --- | --- |
| Capability operation | PASS | PASS | NOT_SUPPORTED |
| Required output shape | PASS | PASS | N/A |
| Usage breakdown | REPORTED | PARTIAL | NOT_SUPPORTED |
| Streaming semantics | PASS | DIFFERENT_CHUNKING | NOT_SUPPORTED |
| Built-in observation | PASS | NOT_SUPPORTED | NOT_SUPPORTED |
| App-level fallback timer | PASS | PASS | PASS |
| Billing reconciliation | MATCHED | PENDING | N/A |

Bảng là **ví dụ minh họa**, không phải kết quả của ba provider cụ thể. DIFFERENT_CHUNKING không nhất thiết là lỗi; nếu ứng dụng chỉ yêu cầu concatenated transcript, adapter có thể chuẩn hóa output nhưng phải giữ metadata chunk nếu nghiệp vụ cần timestamp hoặc speaker.

## 17. Fallback giữa provider phải dựa trên capability và dữ liệu

Fallback không đơn giản là “provider A lỗi thì gọi B”. Cần xem:

- Provider B có hỗ trợ modality/operation không?
- B có nhận cùng input format và options không?
- Model B có cùng semantics output không?
- Usage/billing có được đo không?
- Có giới hạn dữ liệu, region hoặc quyền riêng tư nào không?
- Kết quả B có đạt quality threshold tương đương không?

Ví dụ: STT provider A hỗ trợ speaker diarization nhưng B không hỗ trợ. Nếu ứng dụng chuyển sang B mà không báo, output vẫn có transcript nhưng mất speaker labels. Đó là **capability degradation** cần được ghi nhận.

Một fallback policy có thể phân loại:

| Điều kiện | Hành động |
| --- | --- |
| Timeout/quota tạm thời và B tương thích | Có thể fallback theo retry policy |
| Input format không được B hỗ trợ | Chuyển đổi có kiểm soát hoặc trả lỗi rõ |
| B thiếu capability bắt buộc | Không fallback âm thầm |
| Usage của B không có | Cho phép nếu policy chấp nhận, cost status là UNKNOWN/UNAVAILABLE |
| B chất lượng dưới ngưỡng benchmark | Không dùng cho tác vụ quan trọng |
| Lỗi xác thực/permission | Không thử provider khác bằng credential không được phép |

Khi fallback, tạo một provider call event mới và liên kết cùng logical request. Không ghi đè provider A bằng B; phải giữ attempt, provider, model và cost riêng.

## 18. Chuẩn hóa lỗi nhưng giữ nguyên nguyên nhân

Provider có thể trả HTTP 400, 401, 429, 500; adapter có thể chuyển thành exception khác nhau. Ứng dụng cần một taxonomy chung nhưng vẫn giữ nguyên cause và provider status.

| Internal error class | Ý nghĩa | Hành động thường gặp |
| --- | --- | --- |
| INVALID_REQUEST | Input/options sai | Không retry mù |
| UNAUTHENTICATED | Credential thiếu/sai | Sửa cấu hình |
| FORBIDDEN | Không có quyền | Không fallback trái policy |
| RATE_LIMITED | Vượt quota/rate | Backoff có giới hạn |
| TIMEOUT | Hết thời gian chờ | Kiểm tra request có thể đã được provider nhận |
| PROVIDER_UNAVAILABLE | Provider lỗi/tạm ngừng | Retry/fallback nếu an toàn |
| UNSUPPORTED_CAPABILITY | Model không hỗ trợ option/operation | Chọn model khác hoặc báo rõ |
| INVALID_RESPONSE | Response thiếu/sai schema | Ghi raw metadata có kiểm soát và điều tra |
| SAFETY_REFUSAL | Provider từ chối theo safety policy | Không coi là lỗi hạ tầng |
| CANCELLED | Client/stream hủy | Ghi cancel riêng |

Không mất providerStatusCode, providerErrorCode, requestId và cause khi chuẩn hóa. Một RATE_LIMITED từ provider có thể cần xử lý khác nhau theo retry-after hoặc quota scope.

## 19. Observability: built-in metrics và application metrics có phạm vi khác nhau

Spring AI 2.1.0 cung cấp model observations trong phạm vi provider được hỗ trợ. Với model call, các tín hiệu phổ biến gồm:

- gen_ai.client.operation: thời gian method call và trace context.
- gen_ai.client.token.usage: số token input/output theo dữ liệu model/provider cung cấp, khi có.
- Các low-cardinality keys như operation, provider và request model.
- High-cardinality keys như usage, dimensions, response ID hoặc options được lưu ở trace theo quy định.

Ứng dụng vẫn cần metric riêng để đo:

- tỷ lệ trường usage có mặt;
- số trường bị redacted hoặc unsupported;
- số response invalid/empty;
- số lần fallback và capability degradation;
- số artifact thực sự lưu;
- usage estimate và cost reconciliation delta.

### Metric coverage

Ví dụ định nghĩa:

```text
usage_coverage =
    provider calls with valid reported usage
    / provider calls where usage is expected

capability_coverage =
    requested operations supported by selected model
    / all requested operations

artifact_success_rate =
    validated and persisted artifacts
    / requested artifacts
```

Các tỷ lệ này cần **mẫu số rõ ràng**. Nếu usage không được provider hỗ trợ, không nên đưa call đó vào mẫu số usage_coverage theo cách làm coverage trông thấp giả tạo; có thể báo riêng supported_usage_calls và unsupported_usage_calls.

### Cardinality

Không đưa prompt, transcript, image URL, audio filename, user ID, request ID hoặc provider error message tùy ý vào Prometheus tags. Các trường này có thể nhạy cảm hoặc có cardinality cao. Dùng trace/log có kiểm soát để điều tra request cụ thể.

## 20. Playbook kiểm tra dữ liệu thiếu và provider drift

Khi dashboard hoặc ứng dụng bắt đầu có dữ liệu khác trước:

1. **Chốt phiên bản:** Spring AI BOM, Spring Boot, provider starter, SDK, API version, model ID/deployment.
2. **Xác định operation:** chat, embedding, image, transcription, TTS hoặc vector store.
3. **Kiểm capability:** provider/model có hỗ trợ operation, option, streaming và usage field không?
4. **Kiểm cấu hình thực:** option nào được gửi, option nào default hoặc bị adapter bỏ qua?
5. **Kiểm response metadata:** field vắng, null, zero, empty hay redacted?
6. **Kiểm provenance:** provider-reported, application-measured, locally estimated hay billing export?
7. **Kiểm instrumentation:** built-in observation có hỗ trợ implementation này không; registry/exporter có nhận không?
8. **Kiểm semantics:** unit, input/output direction, batch/request scope và total/component có bị nhầm?
9. **Kiểm quality:** response có hợp lệ và đạt tiêu chí nghiệp vụ không?
10. **Kiểm cost:** price version, billing basis, retry và invoice reconciliation.
11. **Replay fixture:** chạy cùng input trên provider/version cũ và mới, so output và metadata.
12. **Ghi drift:** cập nhật capability profile và contract test; không sửa lịch sử để che thay đổi.

### Ví dụ điều tra

Sau khi chuyển embedding từ OpenAI sang một implementation khác, dashboard không còn gen_ai.client.token.usage:

- Không kết luận model mới không tính token.
- Xác nhận implementation mới có built-in embedding observation theo bảng Spring AI 2.1.0 không.
- Kiểm response metadata có usage không.
- Nếu usage có trong response nhưng counter không xuất hiện, kiểm adapter/ObservationRegistry.
- Nếu provider không báo usage, đánh dấu NOT_REPORTED hoặc NOT_SUPPORTED, dùng billing export khi cần đối soát.
- Vẫn có thể đo model call latency bằng app Timer, nhưng không đặt tên metric đó như built-in gen_ai.client.operation nếu semantics khác.

## 21. Bài tập thực hành

1. **Missing vs zero:** provider không trả output_tokens. Bạn nên lưu 0, null hay trạng thái nào? Vì sao?
2. **Provider capability:** một model có API transcription nhưng không có built-in observation. Hãy phân biệt API support và instrumentation support.
3. **Usage total:** provider trả total_tokens=1.200 nhưng không có input/output split. Những kết luận nào hợp lệ và không hợp lệ?
4. **Image:** model trả URL nhưng không có image usage. Hãy nêu các metric ứng dụng có thể đo và dữ liệu billing cần đối chiếu.
5. **Audio:** STT provider A trả transcript chunks, provider B trả một transcript hoàn chỉnh. Adapter nên chuẩn hóa phần nào và giữ phần nào?
6. **Embedding:** model B trả vector 768 chiều, index yêu cầu 1.024. Vì sao không nên padding số 0 để tiếp tục?
7. **Redaction:** transcript không xuất hiện trong trace do policy. Vì sao không nên coi đó là lỗi instrumentation?
8. **Fallback:** provider A có diarization, provider B không. Thiết kế policy để fallback không âm thầm làm mất speaker labels.
9. **Cost:** provider báo 800 audio seconds nhưng bảng giá dùng phút làm tròn lên. Nêu phép quy đổi và nơi lưu rounding rule.
10. **Contract test:** viết ba assertion bảo đảm provider adapter không biến NOT_REPORTED thành REPORTED_ZERO.
11. **Observability:** có HTTP span nhưng không có gen_ai.client.operation. Liệt kê các nguyên nhân cần kiểm tra.
12. **Provider drift:** sau nâng cấp SDK, usage coverage giảm từ 95% xuống 60%. Thiết kế playbook điều tra.
13. **Cardinality:** vì sao không đưa response ID và prompt vào Prometheus labels?
14. **Version matrix:** lập bảng version × provider × model × operation × capability × observation × usage status cho hệ thống của bạn.

## Tài liệu tham khảo

- [Spring AI 2.1.0 – Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): phạm vi provider được hỗ trợ cho EmbeddingModel, ImageModel, TTS và Transcription; observation, usage, cardinality và bảo vệ dữ liệu.
- [Spring AI – Model APIs](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/models/index.html): shared interfaces và provider-specific options; trang snapshot có thể thay đổi so với stable release.
- [Spring AI 2.1.0 – Text-to-Speech API](https://docs.spring.io/spring-ai/reference/api/audio/speech.html): shared TTS API và provider implementations.
- [Spring AI 2.1.x – Transcription API](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/models/audio/transcription.html): TranscriptionModel, response metadata và provider-specific options; cần đối chiếu stable release đang dùng.
- [Spring AI – Choosing a Model Provider](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/get-started/choose-provider.html): hosted/local provider, switching và provider-specific options.
- [Spring Boot – Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, registry, tags và histogram.
- [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): distributed tracing, sampling và exporter.
- [OpenTelemetry – Semantic Conventions for Generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/): ngữ nghĩa thuộc tính và operation GenAI.

> **Lưu ý phiên bản:** Bảng built-in observability trong bài lấy từ Spring AI 2.1.0 stable. Một số trang API provider tham khảo nhánh 2.1-SNAPSHOT để minh họa rằng capability có thể thay đổi; không dùng snapshot làm hợp đồng cho stable release. Khi triển khai, kiểm tra đúng BOM, provider adapter, model/deployment và runtime telemetry. Các provider matrix mở rộng, schema chuẩn hóa, metric ứng dụng và ví dụ test là thiết kế minh họa, chưa phải kết quả integration test trên dự án.
