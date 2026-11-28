# Quan sát mô hình: Phân biệt token được cache, token thông thường và thông tin không có

## 1. Vì sao cần phân biệt ba trường hợp?

Trong một ứng dụng Spring AI, câu hỏi gửi cho mô hình thường đi kèm system prompt, tool schemas, lịch sử hội thoại và tài liệu RAG. Khi một phần đầu vào lặp lại, một số provider hỗ trợ **prompt caching** để tái sử dụng kết quả xử lý prefix đã gặp trước đó. Caching có thể giúp giảm chi phí hoặc độ trễ, nhưng không đồng nghĩa “mô hình không dùng token”.

Có ba tình huống khác biệt cần giữ riêng khi đánh giá usage:

1. **Token được đọc từ cache** (*cache read*): provider/adapter báo một lượng đầu vào đã được phục vụ từ cache.
2. **Token thông thường** (*ordinary/uncached input*): phần token được xử lý theo nhóm không thuộc cache read/write, theo quy ước provider đã xác minh.
3. **Thông tin không có** (*unavailable/unknown*): response hoặc adapter không cung cấp số liệu cache; không được khẳng định hit bằng 0.

Ngoài ra còn **cache write/cache creation tokens**, tức là token được ghi vào cache để phục vụ những lượt gọi sau. Cache write là một hoạt động khác cache read và có thể bị tính phí theo quy tắc khác.

Ví dụ hai phản hồi có cùng `getPromptTokens() == 1500`:

~~~text
Lượt A:
  promptTokens          = 1500
  cacheReadInputTokens  = 1000
  cacheWriteInputTokens = null

Lượt B:
  promptTokens          = 1500
  cacheReadInputTokens  = null
  cacheWriteInputTokens = null
~~~

Ở lượt A có bằng chứng về **1.000 cached read tokens**. Ở lượt B không có chứng cứ để nói “cache hit bằng 0”: `null` có thể do adapter không hỗ trợ, provider không báo, hoặc không có hoạt động cache theo semantics của API.

Bài này thuộc chương **Quan sát mô hình** của module `SPRING_AI_EVALUATION_OBSERVABILITY`: đánh giá chất lượng Spring AI qua dataset, relevance, fact checking và kiểm thử RAG/tool calling, đồng thời đo metrics, traces, chi phí và độ trễ để truy nguyên thay đổi qua phiên bản prompt/model/pipeline.

**Sau bài học, bạn có thể:**

- Đọc `Usage.getCacheReadInputTokens()` và `getCacheWriteInputTokens()` trong `ChatResponse`.
- Phân biệt **null**, **zero**, **positive**, `EmptyUsage` và số liệu bất thường.
- Hiểu phiên bản Spring AI ảnh hưởng đến `getPromptTokens()` khi có cache.
- Biết khi nào được suy ra số ordinary input, khi nào phải trả `UNKNOWN`.
- Viết mã Java/JUnit phân loại cache usage và phát hiện thiếu dữ liệu.
- Theo dõi cache bằng Micrometer, trace attributes và metric ứng dụng nếu cần.
- Ước lượng chi phí không cộng trùng cache read/write hoặc usage của tool loop.
- Kết hợp cache efficiency với chất lượng phản hồi và độ trễ RAG.

## 2. Các khái niệm và ranh giới

| Khái niệm | Điều nó biểu diễn | Có luôn được provider báo? |
| --- | --- | --- |
| `promptTokens` | Token đầu vào theo giao diện usage chuẩn hóa | Không |
| `completionTokens` | Token đầu ra được báo | Không |
| `totalTokens` | Tổng usage theo giao diện | Không; đôi khi có thể được tính mặc định |
| `cacheReadInputTokens` | Token đầu vào đọc từ cache | Không |
| `cacheWriteInputTokens` | Token đầu vào ghi/tạo cache | Không |
| `ordinaryInputTokens` | Token đầu vào không thuộc phần cache theo quy tắc billing | Không có một getter portable mặc định |
| **Cache hit** | Lượt gọi có ít nhất một phần đầu vào tái sử dụng cache | Chỉ xác định chắc khi có evidence |
| **Cache write** | Tạo/cập nhật cache dùng cho những lần sau | Không phải cache hit |
| **Missing cache data** | Không có số liệu cache được báo | Không được coi như zero |

**Cache hit ở cấp request** khác với **tỷ lệ token được cache**: một request có một token đọc cache và một request có 2.000 token đọc cache đều được tính là “một request có hit”, nhưng lượng token tái sử dụng rất khác nhau.

### 2.1. Cache read và cache write không phải hai tên của cùng số liệu

- `cacheReadInputTokens > 0`: có số token read được báo, tức có bằng chứng sử dụng lại nội dung đã cache.
- `cacheWriteInputTokens > 0`: có số token được báo là ghi vào cache, có thể nhằm dùng trong tương lai.
- Cả hai có thể cùng dương trong một lượt khi provider cho phép đọc một phần prefix và ghi phần mới.
- Một write thành công **không chứng minh** lượt đó đã được hưởng tiết kiệm chi phí do cache read.

### 2.2. Token thông thường có phải luôn bằng promptTokens trừ cacheRead?

**Không.** Có provider biểu diễn native input tokens dưới dạng token uncached riêng; có adapter Spring AI chuẩn hóa tổng input đã bao gồm cache read/write. Khi viết phép trừ, bạn cần biết semantics của **cùng phiên bản provider/adapter**.

Không áp một công thức chung cho OpenAI, Anthropic, Bedrock, Gemini hay custom gateway chỉ vì chúng dùng một giao diện `Usage`.

## 3. Đọc Usage trong Spring AI

Spring AI 2.1.0 cung cấp giao diện `org.springframework.ai.chat.metadata.Usage` với các getter dùng chung:

~~~java
import org.springframework.ai.chat.metadata.Usage;

Integer inputTokens = usage.getPromptTokens();
Integer outputTokens = usage.getCompletionTokens();
Integer totalTokens = usage.getTotalTokens();

Long cacheRead = usage.getCacheReadInputTokens();
Long cacheWrite = usage.getCacheWriteInputTokens();

Object nativeUsage = usage.getNativeUsage();
~~~

Hai getter cache trả `Long` nullable. Giá trị `null` theo tài liệu có thể do provider không hỗ trợ hoặc không cung cấp thông tin tương ứng. Không dùng phép tự động `Objects.requireNonNullElse(cacheRead, 0L)` rồi báo là dữ liệu đo được.

Đường đi của dữ liệu:

~~~mermaid
flowchart TD
    P["Prompt gồm system + user + RAG + tools"] --> M["ChatModel.call hoặc stream"]
    M --> PROVIDER["Provider / model / prompt cache"]
    PROVIDER --> RESPONSE["ChatResponse"]
    RESPONSE --> META["ChatResponseMetadata"]
    META --> USAGE["Usage"]
    USAGE --> IN["getPromptTokens()"]
    USAGE --> OUT["getCompletionTokens()"]
    USAGE --> TOTAL["getTotalTokens()"]
    USAGE --> READ["getCacheReadInputTokens()"]
    USAGE --> WRITE["getCacheWriteInputTokens()"]
    USAGE --> RAW["getNativeUsage()"]
    M --> OBS["gen_ai.client.operation"]
    OBS --> TRACE["Traces / model metrics"]
~~~

Sơ đồ chỉ mô tả luồng **khi provider có gửi metadata phù hợp**. Không phải mọi trường đều hiện diện ở mọi model và chế độ streaming.

### 3.1. Ví dụ Java đọc từ ChatModel

~~~java
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.chat.metadata.Usage;

public final class CacheUsageReader {

    private final ChatModel model;

    public CacheUsageReader(ChatModel model) {
        this.model = model;
    }

    public Usage read(String question) {
        ChatResponse response = model.call(new Prompt(question));

        if (response == null || response.getMetadata() == null) {
            return null;
        }

        return response.getMetadata().getUsage();
    }
}
~~~

Đây là ví dụ minh họa cách đọc; `null` nghĩa là **chưa có Usage để kiểm tra**, không phải model đã xử lý 0 token.

### 3.2. Ví dụ qua ChatClient

~~~java
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.metadata.Usage;

// chatClient đã được cấu hình trước.
ChatResponse response = chatClient.prompt()
        .user("Thời hạn đổi trả online là bao lâu?")
        .call()
        .chatResponse();

Usage usage = response == null || response.getMetadata() == null
        ? null
        : response.getMetadata().getUsage();

if (usage != null) {
    Long read = usage.getCacheReadInputTokens();
    Long write = usage.getCacheWriteInputTokens();
    System.out.println("Cache read: " + read);
    System.out.println("Cache write: " + write);
}
~~~

`call().content()` chỉ trả nội dung văn bản; dùng `chatResponse()` để truy cập usage. Không ghi raw prompt hoặc API key ra log để kiểm tra cache.

## 4. Thay đổi quan trọng của Spring AI từ 2.0.3

Theo **Spring AI Upgrade Notes**, kể từ **Spring AI 2.0.3**, hai adapter **Anthropic** và **Bedrock Converse** tính cả cache read và cache write vào `Usage.getPromptTokens()`, cũng như thuộc tính trace `gen_ai.usage.input_tokens`. Trước thay đổi đó, cách tính prompt tokens ở hai adapter có thể chỉ phản ánh phần uncached.

Với Anthropic, `getTotalTokens()` cũng đã bao gồm cached input; Bedrock đã có provider-reported total chứa các thành phần đó. Hai getter cache riêng vẫn tồn tại.

**Hệ quả:** nếu ứng dụng đã từng “bù cache” bằng cách cộng `cacheRead + cacheWrite` vào `getPromptTokens()`, cần bỏ workaround đó khi dùng các adapter đã chuẩn hóa. Nếu không, bạn **đếm trùng input**.

Ví dụ mô phỏng trên bản Spring AI có logic chuẩn hóa:

~~~text
getPromptTokens()          = 2000
getCacheReadInputTokens()  = 1200
getCacheWriteInputTokens() =  300
getCompletionTokens()      =  180

Tổng theo input + output = 2180

SAI nếu đếm:
  2000 + 1200 + 300 + 180 = 3680
~~~

Số liệu chỉ để minh họa semantics. Nếu so dữ liệu Spring AI 2.0.2 với 2.1.0, cần lưu `springAiVersion` và chuyển đổi hợp lệ hoặc giữ các chuỗi thống kê tách biệt, tránh kết luận prompt dài hơn chỉ vì **cách đếm đã thay đổi**.

### 4.1. Native usage của Anthropic có thể khác số chuẩn hóa

Giả sử response gốc provider có dạng:

~~~json
{
  "usage": {
    "input_tokens": 500,
    "cache_read_input_tokens": 1200,
    "cache_creation_input_tokens": 300,
    "output_tokens": 180
  }
}
~~~

Theo ngữ nghĩa của provider trong trường hợp này, `input_tokens` là phần thông thường, còn read/write cache được báo riêng. Với adapter Spring AI đã chuẩn hóa tổng input, có thể đọc:

~~~text
Spring AI promptTokens     = 500 + 1200 + 300 = 2000
Spring AI cacheReadTokens  = 1200
Spring AI cacheWriteTokens = 300
~~~

**Đây không phải cách ánh xạ bắt buộc của mọi provider.** Muốn phân tích chính xác, đối chiếu dữ liệu native và version của adapter.

## 5. Khả năng map cache usage khác nhau giữa provider

Theo Spring AI Reference 2.1.0:

| Provider adapter | Cache read getter | Cache write getter | Ghi chú |
| --- | --- | --- | --- |
| **Anthropic** | Có | Có | Có dữ liệu cache creation/read |
| **AWS Bedrock** | Có | Có | Theo hỗ trợ API/model tương ứng |
| **OpenAI** | Có | Chưa được bảng hỗ trợ getter liệt kê | SDK/provider API có thể cung cấp chi tiết native khác |
| **Google Gemini** | Có | Chưa được bảng hỗ trợ getter liệt kê | Có thể có breakdown theo modality |
| **DeepSeek** | Không | Không | `null` không chứng minh số read thực tế bằng 0 |
| **Mistral** | Không | Không | Phân biệt thiếu trường và không có hit |
| **Ollama** | Không | Không | Không suy diễn cache nội bộ từ cache getter |
| **Provider khác** | Tùy adapter/version | Tùy adapter/version | Kiểm tra API và metadata thật |

Bảng đề cập **các getter của Spring AI**, không khẳng định provider không thể có một loại cache khác hoặc không có field mới ở API riêng. API và adapter có thể được cập nhật ở thời điểm khác nhau.

### 5.1. Tại sao một provider có cache mà không thấy hit?

Các nguyên nhân có thể là:

- Prompt chưa đủ độ dài tối thiểu để cache.
- Prefix thay đổi do timestamp, request ID, tool schema hoặc thứ tự message.
- TTL hết hạn hoặc entry bị evict.
- Routing sang vùng cache/deployment khác.
- Request chạy ở một model hoặc chế độ không áp dụng caching.
- Provider có hit nhưng adapter chưa ánh xạ metadata.
- Metadata cache chỉ xuất hiện khi lời gọi/stream hoàn tất.

**Một giá trị `null` không đủ để phân biệt các nguyên nhân này.**

## 6. Thiết kế trạng thái UNKNOWN, EXPLICIT_ZERO và POSITIVE

Một hệ thống đáng tin cần lưu **giá trị** và **độ chắc chắn của giá trị đó**.

| Giá trị cache getter | Trạng thái do ứng dụng định nghĩa | Ý nghĩa |
| --- | --- | --- |
| `null` | `UNKNOWN` | Không có con số để kết luận |
| `0L` | `EXPLICIT_ZERO` | Getter trả số 0, cần xem provenance |
| `800L` | `POSITIVE` | Getter báo 800 cached tokens |
| Số âm | `INVALID` | Metadata bất thường |

Số 0 chỉ chứng minh **đầu ra của getter bằng 0**; để khẳng định “provider có hỗ trợ cache và không có hit”, cần xác nhận object đó thật sự ánh xạ số 0 do provider gửi.

### 6.1. EmptyUsage khác 0 do provider báo

Spring AI có `EmptyUsage` trả 0 cho các getter usage cơ bản. Đối tượng này có thể được dùng khi metadata usage không có:

~~~java
import org.springframework.ai.chat.metadata.EmptyUsage;
import org.springframework.ai.chat.metadata.Usage;

Usage usage = new EmptyUsage();

System.out.println(usage.getPromptTokens());      // 0
System.out.println(usage.getCompletionTokens());  // 0
System.out.println(usage.getTotalTokens());       // 0
~~~

**Không tự coi `EmptyUsage` là lời khẳng định provider tiêu thụ đúng 0 token.** Một `Usage` khác thực sự báo 0 có thể tồn tại; phải xét nguồn dữ liệu và tình huống.

### 6.2. Ví dụ Java: snapshot giữ nguyên missing

~~~java
public enum CacheFieldState {
    UNKNOWN,
    EXPLICIT_ZERO,
    POSITIVE,
    INVALID
}
~~~

~~~java
public record CacheQuantity(CacheFieldState state, Long tokens) {

    public static CacheQuantity from(Long raw) {
        if (raw == null) {
            return new CacheQuantity(CacheFieldState.UNKNOWN, null);
        }
        if (raw < 0) {
            return new CacheQuantity(CacheFieldState.INVALID, raw);
        }
        if (raw == 0) {
            return new CacheQuantity(
                    CacheFieldState.EXPLICIT_ZERO, 0L);
        }
        return new CacheQuantity(CacheFieldState.POSITIVE, raw);
    }
}
~~~

~~~java
import org.springframework.ai.chat.metadata.EmptyUsage;
import org.springframework.ai.chat.metadata.Usage;

public final class CacheUsageInspector {

    public record Snapshot(
            boolean usagePresent,
            Integer promptTokens,
            Integer completionTokens,
            Integer totalTokens,
            CacheQuantity read,
            CacheQuantity write) {
    }

    private CacheUsageInspector() {
    }

    public static Snapshot inspect(Usage usage) {
        if (usage == null || usage instanceof EmptyUsage) {
            return new Snapshot(
                    false, null, null, null,
                    CacheQuantity.from(null),
                    CacheQuantity.from(null));
        }

        Integer prompt = usage.getPromptTokens();
        Integer completion = usage.getCompletionTokens();

        // Một số implementation mặc định cộng prompt + completion
        // để tính total. Giữ null khi thiếu dữ liệu thành phần.
        Integer total = prompt != null && completion != null
                ? usage.getTotalTokens()
                : null;

        return new Snapshot(
                true, prompt, completion, total,
                CacheQuantity.from(usage.getCacheReadInputTokens()),
                CacheQuantity.from(usage.getCacheWriteInputTokens()));
    }
}
~~~

**Lớp này do ứng dụng tự viết**, không phải API có sẵn trong Spring AI. `usagePresent=true` chỉ nói có Usage object không phải `EmptyUsage`; **không bảo đảm mọi trường đều có giá trị**. Với provider có total độc lập dù thiếu prompt/output, muốn đọc riêng total phải xác minh implementation và điều chỉnh mã.

### 6.3. JUnit kiểm thử mọi nhóm mà không gọi LLM

Spring AI có `DefaultUsage` constructor sáu tham số gồm `prompt, completion, total, native, cacheRead, cacheWrite`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.metadata.DefaultUsage;
import org.springframework.ai.chat.metadata.EmptyUsage;

import static org.assertj.core.api.Assertions.assertThat;

class CacheUsageInspectorTest {

    @Test
    void missingUsageIsNotZero() {
        var missing = CacheUsageInspector.inspect(null);
        assertThat(missing.usagePresent()).isFalse();
        assertThat(missing.read().state())
                .isEqualTo(CacheFieldState.UNKNOWN);

        var empty = CacheUsageInspector.inspect(new EmptyUsage());
        assertThat(empty.usagePresent()).isFalse();
        assertThat(empty.promptTokens()).isNull();
    }

    @Test
    void positiveReadAndUnknownWriteAreDifferent() {
        var usage = new DefaultUsage(
                2000, 180, 2180, null, 1200L, null);

        var result = CacheUsageInspector.inspect(usage);
        assertThat(result.promptTokens()).isEqualTo(2000);
        assertThat(result.read().state())
                .isEqualTo(CacheFieldState.POSITIVE);
        assertThat(result.read().tokens()).isEqualTo(1200L);
        assertThat(result.write().state())
                .isEqualTo(CacheFieldState.UNKNOWN);
    }

    @Test
    void explicitZeroIsPreserved() {
        var usage = new DefaultUsage(
                1000, 80, 1080, null, 0L, 0L);

        var result = CacheUsageInspector.inspect(usage);
        assertThat(result.read().state())
                .isEqualTo(CacheFieldState.EXPLICIT_ZERO);
        assertThat(result.write().state())
                .isEqualTo(CacheFieldState.EXPLICIT_ZERO);
    }

    @Test
    void canReportBothCacheDirections() {
        var usage = new DefaultUsage(
                2000, 180, 2180, null, 1200L, 300L);

        var result = CacheUsageInspector.inspect(usage);
        assertThat(result.read().tokens()).isEqualTo(1200L);
        assertThat(result.write().tokens()).isEqualTo(300L);
    }

    @Test
    void rejectsNegativeCacheValue() {
        assertThat(CacheQuantity.from(-1L).state())
                .isEqualTo(CacheFieldState.INVALID);
    }
}
~~~

Đây là **unit test phân loại dữ liệu**, không chứng minh provider thật đã trả metadata chính xác. Integration test vẫn cần đối chiếu provider adapter, SDK, chế độ streaming và phiên bản Spring AI.

## 7. Khi nào được tính ordinary input bằng phép trừ?

Một công thức thường được đề xuất:

~~~text
ordinaryInputTokens =
    promptTokens - cacheReadInputTokens - cacheWriteInputTokens
~~~

**Chỉ áp dụng khi tất cả điều kiện sau được kiểm chứng:**

1. `promptTokens` **bao gồm** hai phần cache read/write ở phiên bản adapter đang dùng.
2. Các số read/write là hai nhóm **không chồng lấp** theo provider.
3. Mọi số liệu thuộc **cùng một model call** hoặc aggregate đã được xác nhận cùng cấp.
4. Cả hai trường cache đều có số đáng tin, không dùng `null` thay bằng 0.
5. Không có nhóm token đầu vào khác cần xử lý riêng theo hợp đồng provider.
6. Hiệu số không âm và không vượt các ràng buộc hợp lý.

Ví dụ **giả định đã xác nhận semantics**:

~~~text
promptTokens         = 2000
cacheReadInputTokens = 1200
cacheWriteInputTokens=  300

ordinaryInputTokens  = 2000 - 1200 - 300 = 500
~~~

Nhưng nếu `cacheWrite == null` thì kết quả **UNKNOWN**, không mặc định là `2000 - 1200`. Nếu phép trừ cho số âm, ghi `INCONSISTENT_USAGE` rồi điều tra adapter/provider; không âm thầm dùng `Math.max(0, value)`.

### 7.1. Bộ kiểm tra phòng thủ bằng Java

~~~java
public final class OrdinaryInputCalculator {

    private OrdinaryInputCalculator() {
    }

    // Chỉ gọi khi provider contract đã xác nhận:
    // prompt includes cache, read/write không chồng lấp.
    public static Long derive(
            int promptTokens, Long read, Long write,
            boolean verifiedAccounting) {

        if (!verifiedAccounting || promptTokens < 0
                || read == null || write == null) {
            return null; // UNKNOWN, không thể suy ra
        }

        if (read < 0 || write < 0) {
            throw new IllegalArgumentException("Cache count âm");
        }

        long remainder = (long) promptTokens - read - write;

        if (remainder < 0) {
            throw new IllegalStateException(
                    "Cache tokens vượt quá prompt tokens");
        }

        return remainder;
    }
}
~~~

Đây là logic **theo một bộ giả định đã kiểm chứng**, không phải phép tính Spring AI tự thực hiện. Trong thực tế, ứng dụng nên cấu hình `verifiedAccounting` theo provider/version đã được kiểm toán, không để người gọi tùy ý đánh dấu `true`.

## 8. Đừng cộng trùng cache khi tính total tokens hoặc chi phí

Nếu `getPromptTokens()` đã bao gồm cache reads/writes thì:

~~~text
promptTokens       = 2000
completionTokens   = 180
totalTokens        = 2180

cacheReadTokens    = 1200   // breakdown của input
cacheWriteTokens   = 300    // breakdown của input

KHÔNG tính total = 2180 + 1200 + 300
~~~

Cache breakdown là **phân loại đầu vào**, không nhất thiết là token bổ sung ngoài tổng.

### 8.1. Ước lượng chi phí theo nhóm có đơn giá khác

Một công thức chỉ hợp lệ khi đã xác nhận các nhóm đầu vào **tách biệt**:

~~~text
estimatedCost =
    ordinaryInputTokens / 1_000_000 * ordinaryInputRate
  + cacheReadTokens     / 1_000_000 * cacheReadRate
  + cacheWriteTokens    / 1_000_000 * cacheWriteRate
  + outputTokens        / 1_000_000 * outputRate
~~~

Các provider có thể có nhiều mức giá cache theo TTL, modality hoặc loại API; khi đó cần phân nhóm chi tiết hơn. `getNativeUsage()` có thể hữu ích nếu adapter giữ được dữ liệu gốc.

Ví dụ **đơn giá hoàn toàn giả định**:

| Loại | Token | Giá USD / triệu token |
| --- | ---: | ---: |
| Ordinary input | 500 | 2,00 |
| Cache read input | 1.200 | 0,20 |
| Cache write input | 300 | 2,50 |
| Output | 180 | 8,00 |

~~~text
Ordinary =  500 / 1.000.000 * 2,00 = 0,00100 USD
Read     = 1200 / 1.000.000 * 0,20 = 0,00024 USD
Write    =  300 / 1.000.000 * 2,50 = 0,00075 USD
Output   =  180 / 1.000.000 * 8,00 = 0,00144 USD
Estimated total                     = 0,00343 USD
~~~

Con số chỉ để luyện cách tính, **không phải giá hiện hành của OpenAI, Anthropic hay Bedrock**. Nếu `cacheWrite` thiếu, không được tự dùng mức giá write là 0. Khi cần hóa đơn chuẩn, đối chiếu báo cáo billing chính thức của nhà cung cấp.

### 8.2. Đánh giá lợi ích cache qua nhiều lượt, không chỉ một write

Một lượt ghi cache có thể bị tính phí cao hơn ordinary input, nhưng nhiều lượt đọc sau có thể tiết kiệm. Khi phân tích, cần cộng **chi phí tạo cache + chi phí các lượt đọc + lượt hết hạn/không hit** trên cùng cửa sổ quan sát; không tuyên bố tiết kiệm ngay chỉ vì có cacheWrite > 0.

## 9. Cache-hit rate và tỷ lệ token được tái sử dụng

Hai chỉ số thường bị nhầm:

| Chỉ số | Công thức điều kiện | Mục đích |
| --- | --- | --- |
| **Request hit rate** | Số calls có `read > 0` / số calls **đã biết read status** | Bao nhiêu lượt có ít nhất một cache read? |
| **Cached-input fraction** | Tổng cacheRead / tổng promptTokens trên **cùng tập đo đủ** | Tỷ phần token input được đọc cache |
| **Cache write rate** | Tổng cacheWrite / thời gian | Đang tạo thêm bao nhiêu cache? |
| **Usage coverage** | Số calls có cache metadata / tổng calls kỳ vọng | Có đủ bằng chứng để phân tích không? |

Ví dụ bốn lượt:

| Call | Prompt tokens | Cache read | Cách xử lý |
| --- | ---: | ---: | --- |
| A | 1.000 | 700 | Biết positive |
| B | 2.000 | 0 | Biết explicit zero |
| C | 1.500 | `null` | **Thiếu dữ liệu** |
| D | 500 | 300 | Biết positive |

Với điều kiện prompt tokens đã bao gồm cached reads và chỉ xét A, B, D:

~~~text
cached-input fraction = (700 + 0 + 300) / (1000 + 2000 + 500)
                      = 1000 / 3500
                      ≈ 28,57%

request hit rate      = 2 / 3 ≈ 66,67%
coverage              = 3 / 4 = 75%
~~~

**Không đưa C vào mẫu số như thể read=0**. Nếu làm vậy, tỷ lệ cached-input fraction bị kéo xuống sai lệch. Cũng không dùng `2/3` làm tỷ lệ hit **của mọi request** vì số liệu của C còn thiếu.

### 9.1. Request đủ điều kiện cache vẫn có thể không hit

Cache hit phụ thuộc TTL, độ dài tối thiểu và nội dung prefix. Các chỉ số `eligibleCalls` và `callsWithReportedCache` khác nhau. Muốn tính hiệu quả tối ưu cache, tốt nhất giữ thêm tỷ lệ lượt gọi đủ điều kiện, không chỉ số lần `read>0`.

Các trạng thái đề xuất `CACHE_ELIGIBLE`, `CACHE_INELIGIBLE`, `CACHE_STATUS_UNKNOWN` là **thiết kế của ứng dụng**, không phải enum Spring AI.

## 10. Traces và metrics: lấy dữ liệu cache ở đâu?

Spring AI sử dụng Micrometer Observation cho thao tác `ChatModel`, thường mang tên `gen_ai.client.operation`. Các dữ liệu usage có thể được ghi trong **trace attributes**:

| Trace attribute | Ý nghĩa |
| --- | --- |
| `gen_ai.usage.input_tokens` | Input tokens theo số đã chuẩn hóa |
| `gen_ai.usage.output_tokens` | Output tokens |
| `gen_ai.usage.total_tokens` | Tổng usage |
| `gen_ai.usage.cache_read.input_tokens` | Token đọc từ cache |
| `gen_ai.usage.cache_creation.input_tokens` | Token ghi/tạo cache |

**Không phải mọi provider/response đều có đủ những thuộc tính này.** Trong Spring AI Reference, đây là nhóm thuộc tính được mô tả cho model observation; khi dữ liệu không có, không nên suy diễn giá trị 0.

Ở tầng metrics, Spring AI có `gen_ai.client.token.usage`. Khi xuất Prometheus, counter thường có tên:

~~~text
gen_ai_client_token_usage_total
~~~

Các giá trị `gen_ai_token_type=input`, `output` và `total` phản ánh nhóm token tiêu chuẩn. **Không tự cho rằng counter này đã tách riêng `cache_read` và `cache_write`**; hai trường cache có thể nằm trong trace hoặc cần instrumentation ứng dụng bổ sung.

### 10.1. Vì sao không dùng raw trace làm tỷ lệ cache production?

Traces có thể được **sampling**, ví dụ chỉ lấy 10% requests. Một vài trace chứa `cacheRead>0` hữu ích để chẩn đoán, nhưng không tự đại diện toàn bộ traffic. Để tính hit rate production, cần nguồn dữ liệu có coverage ổn định, như counters do ứng dụng ghi tại đúng một điểm đo hoặc báo cáo chính thức từ provider.

**Chọn đúng mẫu số:** một `ChatClient` request có thể tạo nhiều `ChatModel` calls do tool calling. Cache read per **model call** khác cache read per **user request**. Nếu một user request gọi model ba lần, không thể lấy call hit rate rồi đặt tên là user hit rate.

### 10.2. Prometheus có input, output và total

Ví dụ query lấy tốc độ input token theo provider:

~~~promql
sum by (gen_ai_system) (
  rate(gen_ai_client_token_usage_total{
    gen_ai_operation_name="chat",
    gen_ai_token_type="input"
  }[5m])
)
~~~

Query lấy output tokens:

~~~promql
sum by (gen_ai_system) (
  rate(gen_ai_client_token_usage_total{
    gen_ai_operation_name="chat",
    gen_ai_token_type="output"
  }[5m])
)
~~~

Với metric có các nhóm `input`, `output` và `total`, **không cộng cả ba** vì `total` đã biểu diễn tổng. Chỉ dùng `total`, hoặc cộng input/output khi cần và chắc chắn cả hai có dữ liệu.

Việc counter token không tăng trong một khoảng **không chứng minh model không dùng token**: lượt gọi có thể thiếu usage. Timer `gen_ai.client.operation` vẫn có thể tăng số lượt gọi hoàn tất.

## 11. Ví dụ Micrometer: tự tạo cache metrics có coverage

Nếu cần dashboard cache theo provider, ứng dụng có thể tạo **counter riêng** từ `CacheUsageInspector.Snapshot`. Ví dụ dùng số nhãn hữu hạn, không ghi user ID hay raw prompt:

~~~java
import io.micrometer.core.instrument.MeterRegistry;

public final class CacheObservationMetrics {

    private final MeterRegistry meters;

    public CacheObservationMetrics(MeterRegistry meters) {
        this.meters = meters;
    }

    public void record(String provider,
            CacheUsageInspector.Snapshot snapshot) {

        // provider phải đến từ allowlist/bean config, không lấy
        // trực tiếp từ trường văn bản do người dùng nhập.
        if (!snapshot.usagePresent()) {
            meters.counter(
                    "application.cache.usage.calls",
                    "provider", provider,
                    "kind", "all",
                    "status", "USAGE_MISSING"
            ).increment();
            return;
        }

        recordField(provider, "read", snapshot.read());
        recordField(provider, "write", snapshot.write());
    }

    private void recordField(
            String provider,
            String kind,
            CacheQuantity quantity) {

        meters.counter(
                "application.cache.usage.calls",
                "provider", provider,
                "kind", kind,
                "status", quantity.state().name()
        ).increment();

        if (quantity.state() == CacheFieldState.POSITIVE) {
            meters.counter(
                    "application.cache.usage.tokens",
                    "provider", provider,
                    "kind", kind
            ).increment(quantity.tokens());
        }
    }
}
~~~

Đây là **metric của ứng dụng**, không phải metric mặc định Spring AI. Cần gắn nó vào **một điểm ghi duy nhất cho mỗi model call** để không đếm trùng. Không ghi thêm usage tổng của ChatClient như một model call mới nếu các child calls đã được ghi.

### 11.1. Thêm thống kê về dữ liệu thiếu

Có thể định nghĩa:

| Counter tự tạo | Khi tăng |
| --- | --- |
| `application.cache.usage.calls{status="USAGE_MISSING"}` | Không có `Usage` đọc được |
| `application.cache.usage.calls{kind="read",status="UNKNOWN"}` | Không có số read |
| `application.cache.usage.calls{kind="read",status="EXPLICIT_ZERO"}` | Có số read bằng 0 |
| `application.cache.usage.calls{kind="read",status="POSITIVE"}` | Có số read dương |
| `application.cache.usage.calls{kind="write",status="POSITIVE"}` | Có số write dương |
| `application.cache.usage.tokens{kind="read"}` | Số token read dương được ghi |

Không nên dùng tên metric mà không xác nhận việc Micrometer/Prometheus chuẩn hóa thành series tương ứng. Ví dụ timer và counter có những hậu tố khác nhau theo registry.

### 11.2. PromQL cho metric tự tạo

Giả sử counter token custom được xuất thành `application_cache_usage_tokens_total`, có thể lấy cache read tokens/phút:

~~~promql
sum by (provider) (
  rate(application_cache_usage_tokens_total{
    kind="read"
  }[5m])
) * 60
~~~

Token cache write/phút:

~~~promql
sum by (provider) (
  rate(application_cache_usage_tokens_total{
    kind="write"
  }[5m])
) * 60
~~~

Tỷ lệ calls **có read dương trên các calls có read được báo**:

~~~promql
sum by (provider) (
  rate(application_cache_usage_calls_total{
    kind="read",
    status="POSITIVE"
  }[5m])
)
/
sum by (provider) (
  rate(application_cache_usage_calls_total{
    kind="read",
    status=~"POSITIVE|EXPLICIT_ZERO"
  }[5m])
)
~~~

Mẫu số không bao gồm `UNKNOWN`, vì thế tên biểu đồ phải ghi rõ **“cache read positive rate on reported calls”**, không phải “cache hit rate trên mọi lượt gọi”.

Khi mẫu số bằng 0 hoặc không có series, hiển thị **không đủ dữ liệu** thay vì gán 0%. Trước khi dùng trong sản phẩm, kiểm tra chính xác tên series và labels tại `/actuator/prometheus`.

## 12. Tình huống RAG: prompt dài nhưng cache read thấp

RAG có thể đưa các tài liệu khác nhau vào prompt ở mỗi yêu cầu. Một prompt ví dụ gồm:

~~~text
[System instructions cố định]
[Định nghĩa các tools]
[Lịch sử hội thoại]
[Các chunk được truy xuất của lượt này]
[Câu hỏi hiện tại]
~~~

Phần **system instructions/tool definitions** thường ổn định hơn các chunk RAG. Một số provider có cơ chế cache theo prefix, nên **vị trí và thứ tự các phần của prompt** có thể ảnh hưởng cache reuse.

### 12.1. Những nguyên nhân làm prefix thay đổi liên tục

- Chèn timestamp hoặc request ID vào đầu system prompt.
- Thay đổi thứ tự tool definitions giữa các lần gọi.
- Serialize một map thành JSON với thứ tự keys không ổn định.
- Đặt nội dung truy xuất động trước phần hướng dẫn lặp lại.
- Ghi metadata của người dùng vào đầu các prompt giống nhau.
- Đổi model, phiên bản template, cache settings hoặc routing.
- Cache entry hết TTL hoặc request không đủ điều kiện cache.

Ví dụ gợi ý:

~~~text
Ít ổn định:
  [timestamp] [system] [tool schemas] [RAG] [question]

Có thể ổn định hơn:
  [system cố định] [tool schemas cố định] [RAG] [question]
~~~

Đây là **gợi ý để thử nghiệm**, không phải cam kết cách bố trí duy nhất luôn tối ưu với mọi provider. Caching có thể còn phụ thuộc các giới hạn độ dài, TTL, cache breakpoints và quy tắc của SDK.

### 12.2. Tối ưu cache không đồng nghĩa tối ưu relevance

Giả sử sau khi tăng số chunk RAG:

| Chỉ số giả định | Pipeline A | Pipeline B |
| --- | ---: | ---: |
| Input tokens trung bình/case | 1.200 | 2.200 |
| Cache read tokens trung bình/case | 500 | 900 |
| P95 answer latency | 1,4 giây | 1,9 giây |
| Relevance pass rate | 82% | 84% |
| Retrieval source coverage | 90% | 92% |

B có nhiều cached tokens hơn, nhưng tổng input và latency cũng tăng. Không thể kết luận B tốt hơn chỉ vì cache read tăng. Cần so **chi phí thực/ước lượng, nguồn liên quan, sự đầy đủ của câu trả lời và chất lượng theo nhãn chuyên gia**.

Nếu judge model hoặc rubric cũng đổi trong phép thử, tỷ lệ relevance không còn là thước đo ổn định để kết luận tác động của cache/prompt.

## 13. Tool calling: aggregate Usage có thể đã chứa cache read/write

Một lượt `ChatClient` có thể gọi mô hình hai lần trong vòng tool calling, sau đó trả một `ChatResponse` cuối với usage cộng dồn.

~~~mermaid
sequenceDiagram
    participant U as User
    participant CC as ChatClient
    participant CM as ChatModel
    participant TOOL as Tool
    U->>CC: Hỏi trạng thái đơn
    CC->>CM: Model call #1
    CM-->>CC: Tool request + Usage #1
    CC->>TOOL: getOrderStatus
    TOOL-->>CC: Tool result
    CC->>CM: Model call #2
    CM-->>CC: Final answer + Usage #2
    CC-->>U: ChatResponse + aggregated Usage
~~~

Spring AI 2.1.0 mô tả `UsageCalculator` tổng hợp **standard input/output/total** và các trường cache read/write của nhiều model calls. Object native usage không thể gộp chung một cách tổng quát và có thể là `null` sau multi-call aggregation.

Ví dụ **chỉ để tính**:

| Cấp | Input | Cache read | Cache write | Output |
| --- | ---: | ---: | ---: | ---: |
| Model call #1 | 600 | 300 | 0 | 40 |
| Model call #2 | 900 | 450 | 100 | 120 |
| **ChatClient aggregate** | **1500** | **750** | **100** | **160** |

Nếu báo chi phí cho **một ChatClient exchange**, dùng dòng aggregate **hoặc** tổng hai model calls; **không cộng cả ba dòng**.

### 13.1. Judge usage không mặc nhiên nằm trong answer aggregate

Một bài đánh giá RAG có thể thực hiện:

~~~text
Answer ChatClient exchange: usage đã tổng hợp nhiều calls
RelevancyEvaluator:         một lượt judge model khác
FactCheckingEvaluator:      có thể thêm lượt judge nữa
Embedding / retrieval:      usage riêng nếu provider/model có báo
~~~

Nếu muốn chi phí **toàn bộ evaluation case**, cần cộng **những phần không chồng lấp** và lưu nhãn vai trò `answer`, `judge`, `embedding`. Khi so sánh chất lượng, cố định judge model và rubric nếu mục tiêu là đánh giá sự thay đổi của answer model/prompt.

### 13.2. Vì sao native usage thiếu sau tool loop không phải lỗi?

Một object native OpenAI không thể đại diện trung thực cho hai response riêng, đặc biệt khi chúng có những breakdown khác nhau. Spring AI có thể giữ standard usage cộng dồn trong `getPromptTokens()` và cache getters, còn `getNativeUsage()` là `null`.

**Không suy ra cache usage bằng 0 vì `getNativeUsage() == null`.** Kiểm tra hai cache getter chuẩn trước; nếu cần breakdown chuyên biệt từng lượt, instrument từng `ChatModel` call.

## 14. Streaming, cancel và lỗi kỹ thuật

Với `ChatClient.stream().chatResponse()`, một `Flux<ChatResponse>` có thể chứa các chunks với metadata từng phần. Một số provider chỉ trả usage ở cuối stream; khi kết nối lỗi hoặc người dùng hủy sớm, usage có thể không được nhận đầy đủ.

**Không cộng cache counts trong mọi chunk một cách máy móc:**

~~~java
// PHẢN VÍ DỤ: có thể vừa NPE vừa đếm trùng.
long totalRead = chunks.stream()
        .mapToLong(c -> c.getMetadata()
                .getUsage().getCacheReadInputTokens())
        .sum();
~~~

Đoạn này sai về giả định: số usage trong từng chunk không nhất thiết là **phần tăng mới**, getter có thể `null` và dữ liệu cuối có thể không đến.

### 14.1. Phân loại trạng thái luồng

| Trạng thái ứng dụng | Ý nghĩa |
| --- | --- |
| `STREAM_COMPLETED` | Đã nhận tín hiệu kết thúc bình thường |
| `STREAM_CANCELLED` | Subscriber hủy trước khi kết thúc |
| `STREAM_ERROR` | Publisher có `onError` |
| `USAGE_COMPLETE` | Có đủ usage theo tiêu chí ứng dụng |
| `USAGE_PARTIAL` | Chỉ một phần dữ liệu token/cache |
| `USAGE_UNKNOWN` | Không có bằng chứng để kết luận |

Các tên này không phải enum usage mặc định trong Spring AI. Nếu không có usage do cancel/error, **không gán 0 USD** cho lượt gọi đó; provider có thể đã xử lý và tính phí một phần. Khi cần đối chiếu billing chính xác, xem báo cáo từ phía provider.

### 14.2. Một stream có read nhưng không có write metadata

Có thể gặp `cacheRead > 0` khi write missing. Ghi **read known, write unknown**; đừng giả định write=0, nhất là nếu adapter hiện chỉ có getter read. Tương tự, nếu thấy write > 0 và read null, không được gọi đó là cache hit.

## 15. Bản ghi usage để so sánh phiên bản

Một case evaluation nên lưu đủ dữ liệu để phân tích **chất lượng, chi phí và coverage**:

~~~json
{
  "caseId": "return-policy-051",
  "datasetVersion": "rag-eval-v7",
  "workflowRole": "answer",
  "springAiVersion": "2.1.0",
  "provider": "example-provider",
  "requestedModel": "answer-model-alias",
  "reportedModel": "answer-model-revision",
  "promptVersion": "answer-v12",
  "retrieverVersion": "retriever-v5",
  "usageState": "REPORTED",
  "promptTokens": 2000,
  "completionTokens": 180,
  "totalTokens": 2180,
  "cacheReadInputTokens": 1200,
  "cacheWriteInputTokens": null,
  "cacheReadState": "POSITIVE",
  "cacheWriteState": "UNKNOWN",
  "ordinaryInputTokens": null,
  "latencyMs": 1220,
  "relevancePass": true
}
~~~

Đây là **schema do ứng dụng tự thiết kế**, không phải payload Spring AI tự động xuất. `ordinaryInputTokens=null` là có chủ đích: chưa có số write nên không thể xác minh phép trừ. `relevancePass=true` chỉ là một nhãn đánh giá trong ví dụ, không chứng minh câu trả lời đã đúng sự thật ngoài ngữ cảnh.

### 15.1. Phân biệt nguồn số liệu

Một record production có thể cần:

- `usageOrigin=PROVIDER_REPORTED` hoặc `ESTIMATED`.
- `cacheMetricsOrigin=SPRING_AI_ADAPTER`, `NATIVE_SDK` hoặc `UNAVAILABLE`.
- `accountingRulesVersion` xác định cache read/write đã nằm trong input chưa.
- `pricingRulesVersion` và đơn vị tiền tệ.
- `traceId`, role của model call và trạng thái streaming.
- `rawMetadataAvailable` nếu có lưu dữ liệu gốc theo chính sách bảo mật.

Không gắn `caseId` duy nhất hoặc request UUID làm Prometheus low-cardinality label. Dùng trace/log có kiểm soát để truy vết từng case.

## 16. Bảo mật: không cần ghi raw prompt để biết cache tokens

Spring AI mặc định không xuất nội dung prompt/completion vì chúng có thể nhạy cảm. Các cờ liên quan:

~~~properties
spring.ai.chat.observations.log-prompt=false
spring.ai.chat.observations.log-completion=false
spring.ai.chat.client.observations.log-prompt=false
spring.ai.chat.client.observations.log-completion=false
~~~

Thông thường, để biết cache read/write chỉ cần `Usage` metadata, không cần ghi nội dung thật của system prompt, tài liệu RAG hay lời nhắn người dùng.

Tránh đưa vào metric labels:

- API key, bearer token hoặc endpoint có secret.
- Email, số điện thoại, ID người dùng, mã đơn hàng.
- Prompt, completion, tool arguments, tài liệu RAG.
- Request ID hay case ID duy nhất.
- Tên model/deployment do người dùng nhập tùy ý, không giới hạn số giá trị.

Nếu cần nghiên cứu cache miss sâu hơn, hãy so sánh **phiên bản prompt hoặc checksum có kiểm soát** thay vì lưu nguyên prompt production. Khi thực sự cần raw content, phải có phê duyệt, redaction, retention và giới hạn quyền truy cập thích hợp.

## 17. Chẩn đoán các vấn đề thường gặp

| Hiện tượng | Không nên kết luận ngay | Hướng điều tra |
| --- | --- | --- |
| `cacheRead=null` | Provider chắc chắn có 0 hit | Kiểm tra adapter hỗ trợ, metadata native và trạng thái stream |
| `cacheRead=0` | Cache bị tắt hoặc provider hỏng | Kiểm tra dữ liệu có thật từ provider, prompt eligibility và TTL |
| `cacheWrite>0`, read chưa có | Đã tiết kiệm chi phí | Chờ dữ liệu read và tính chi phí tạo cache |
| Input tokens tăng sau upgrade | Prompt dài hơn | Đối chiếu thay đổi accounting Spring AI 2.0.3 |
| ordinary input tính ra âm | Ordinary = 0 | Kiểm tra sai giả định token groups, cùng phạm vi model calls |
| Cache read giảm sau đổi prompt | Adapter hỏng | Xem sự thay đổi prefix, tool definitions, TTL, routing |
| Cost tăng dù total tokens ổn định | Model dùng nhiều hơn | Xem cache pricing mix, rate version và retries |
| Token counter thiếu cache breakdown | Không có caching | Kiểm tra trace attributes hoặc thêm custom metrics |
| Cache read dương, latency vẫn cao | Cache vô dụng | Xem network, output tokens, tool loops, provider load |
| Cache read cao nhưng relevance giảm | Cache gây sai câu trả lời | Kiểm tra dataset, context, prompt và judge |
| Native usage null sau tool loop | Cache information đã mất hết | Đọc standard aggregate getters hoặc từng model call |
| Stream cancel và thiếu usage | Lượt gọi chắc chắn miễn phí | Đối chiếu provider billing |
| Mọi usage đều là 0 | Model tiêu 0 token | Kiểm tra `EmptyUsage`, mocks và missing metadata |

### 17.1. Quy trình gỡ lỗi khi cache read giảm

1. Xác nhận `getUsage()` tồn tại, object không phải `EmptyUsage`.
2. Xem `cacheRead` là số thật, `0L`, hay `null`; ghi trạng thái tương ứng.
3. Kiểm tra provider/model, Spring AI version, adapter và SDK.
4. Kiểm tra `getPromptTokens()` đã gồm cache tokens theo version chưa.
5. Kiểm tra prefix prompt, system messages, thứ tự tools và RAG context.
6. Kiểm tra TTL/eligibility, backend routing và traffic composition.
7. So read/write counts, latency, token usage và estimated cost.
8. Đối chiếu chất lượng RAG và judge trên cùng dataset.
9. Ghi nguyên nhân có bằng chứng, đánh dấu `UNKNOWN` nếu chưa xác minh.

## 18. Bài tập thực hành

### Bài 1. Phân loại metadata

Tạo ba `DefaultUsage` có `cacheRead = null`, `0L` và `750L`. Dùng `CacheUsageInspector` để phân loại. Giải thích vì sao `null` không được đổi thành 0.

### Bài 2. Kiểm thử thay đổi version

Giả sử một pipeline dùng Spring AI 2.0.2 và phiên bản khác dùng 2.1.0 với adapter Anthropic. Thiết kế bảng quy tắc accounting để bảo đảm so sánh prompt tokens không nhầm do thay đổi cách tính cached input.

### Bài 3. Tính ordinary theo điều kiện

Với input=2.000, read=1.200, write=300 và hai cache groups đã được xác nhận không chồng lấp, tính ordinary. Sau đó thử write=null và read=2.500, giải thích khi nào là `UNKNOWN` và khi nào là `INVALID`.

### Bài 4. Cache write và chi phí

Dùng đơn giá giả định ở phần 8. Tính chi phí nhóm ordinary/read/write/output. Thử trường hợp cache write bị tính giá riêng theo TTL và nêu lý do không được dùng một rate nếu chưa có breakdown.

### Bài 5. Prometheus cache metrics

Tạo metric custom như phần 11, kiểm tra output `/actuator/prometheus`. Vẽ cache read tokens/phút, write tokens/phút và tỷ lệ positive read **trên mẫu có reporting**, đồng thời hiển thị missing data.

### Bài 6. RAG prefix ổn định

Tạo dataset 20 câu hỏi có các chunk RAG khác nhau. So hai cách lắp prompt với system/tool prefix ổn định và không ổn định. Đo cache read/write, latency, token và relevance; giữ judge model/rubric cố định.

### Bài 7. Tool calling và judge

Một ChatClient gọi model hai lần trong tool loop, sau đó `RelevancyEvaluator` gọi judge riêng. Đọc aggregate usage và usage từng model call, xác định phần được cộng một lần để tính toàn case.

### Bài 8. Streaming bị hủy

Trong integration test, chủ động hủy stream giữa chừng. Xem có usage cuối không và ghi `USAGE_PARTIAL` hoặc `USAGE_UNKNOWN` thích hợp; không gán tiền bằng 0 khi thiếu metadata.

## 19. Tổng kết

Ba nguyên tắc quan trọng:

1. **Cache read**, **cache write** và **ordinary input** là các khái niệm khác nhau; read dương là bằng chứng tái sử dụng cache, write dương là bằng chứng tạo cache, còn ordinary cần quy tắc provider để xác định.
2. **Không có dữ liệu không phải bằng 0.** `null`, `EmptyUsage`, `0L` và số dương phải được phân loại riêng. Dashboard cần công khai coverage của cache metrics.
3. **Không cộng trùng usage.** Từ Spring AI 2.0.3, Anthropic/Bedrock đã đưa cached input vào `getPromptTokens()`; đừng cộng lại cache read/write. Không cộng aggregate ChatClient với các child calls khi tổng hợp chi phí.

Khi đánh giá ứng dụng Spring AI bằng relevance, fact checking và dữ liệu RAG/tool calling, hãy đặt cache usage bên cạnh **chất lượng đầu ra, latency, token, chi phí và phiên bản prompt/model/pipeline**. Caching giúp tối ưu vận hành nhưng tự nó không xác nhận dữ liệu retrieval đúng hay câu trả lời phù hợp.

## Tài liệu tham khảo

- [Spring AI Reference — Chat Response Metadata / Prompt Cache Usage Metrics](https://docs.spring.io/spring-ai/reference/api/usage-handling.html): các cache getters, bảng provider, cumulative usage và native usage trong tool calling.
- [Spring AI Upgrade Notes — Prompt Token Usage with Caching](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/upgrading/spring-ai-2-0.html): thay đổi ở Spring AI 2.0.3 đối với Anthropic và Bedrock.
- [Spring AI API — Usage](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/metadata/Usage.html): `getPromptTokens()`, `getCacheReadInputTokens()`, `getCacheWriteInputTokens()`.
- [Spring AI API — DefaultUsage](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/metadata/DefaultUsage.html): constructor sáu tham số và các trường cache.
- [Spring AI API — EmptyUsage](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/metadata/EmptyUsage.html): placeholder usage trả 0.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): ChatModel observation, cache trace attributes và token metrics.
- [OpenAI API — Prompt Caching](https://developers.openai.com/api/docs/guides/prompt-caching): các loại token cache và cách diễn giải breakdown theo API/provider.
- [Claude Platform Docs — Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching): native usage của cache creation/read, TTL và tính chi phí theo nhóm.

