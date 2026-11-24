# Chọn vị trí bắt lỗi trong chuỗi hàm

## 1. Mục tiêu bài học

Khi ghép nhiều `Function` trong Spring Cloud Function, một lỗi có thể xuất hiện ở bước chuẩn hóa, xác thực, tính toán, truy cập tài nguyên ngoài hoặc ghi dữ liệu. Câu hỏi không chỉ là **bắt loại ngoại lệ nào** mà còn là **bắt ở đâu để hệ thống không che giấu lỗi và không làm sai trạng thái nghiệp vụ**.

Trong module **SPRING_CLOUD_FUNCTION**, chúng ta xây dựng logic bằng `Supplier`, `Function` và `Consumer`, đăng ký qua `FunctionCatalog`, ghép thành pipeline và tái sử dụng qua Java, HTTP, hệ thống sự kiện hoặc serverless. Vì vậy, mỗi lớp có thể có trách nhiệm xử lý lỗi khác nhau: lõi nghiệp vụ biết *vì sao một yêu cầu không hợp lệ*; adapter biết *phải trả HTTP status, ack, retry hay chuyển vào dead-letter*.

Bài thuộc chương **Độ tin cậy**, tập trung vào cách **chọn vị trí bắt lỗi trong chuỗi hàm**. Sau khi học, bạn có thể:

- Xác định bước phát sinh lỗi, bước có quyền phục hồi và ranh giới chịu trách nhiệm phản hồi.
- Phân biệt `throw` trong Function imperative với `onError` của Reactor khi thực thi reactive.
- Quyết định khi nào dùng `try/catch` cục bộ, một lớp orchestration bao ngoài, hoặc handler ở adapter.
- Tránh nuốt exception trong Consumer, đặc biệt khi database/broker đã tạo tác dụng phụ.
- Chọn vị trí `onErrorResume`, `onErrorMap`, `doOnError` và `retryWhen` theo phạm vi mong muốn.
- Phân loại lỗi dữ liệu, lỗi xung đột và lỗi hạ tầng để áp dụng retry phù hợp.
- Kiểm thử được cả **kết quả** lẫn **việc side effect có hoặc không xảy ra**.

> **Nguyên tắc:** Đặt xử lý lỗi ở tầng có đủ thông tin để **ra quyết định đúng**. Bắt lỗi gần nơi phát sinh để bổ sung ngữ cảnh hoặc phục hồi thật sự; truyền lỗi lên tầng gọi nếu tầng đó mới biết cách phản hồi, retry hay khôi phục.

## 2. Nơi lỗi phát sinh khác nơi lỗi được xử lý

Xét pipeline:

~~~text
OrderRequest
     |
     v
validateOrder                  Function<OrderRequest, ValidatedOrder>
     |
     v
calculateQuote                 Function<ValidatedOrder, Quote>
     |
     v
saveQuote                      Consumer<Quote>
     |
     v
Kết thúc (không có output nghiệp vụ)
~~~

Một yêu cầu có `quantity=0` sẽ thất bại ở validation. Một phép tính có thể lỗi tràn số. Một database có thể timeout khi ghi. Cả ba lỗi không nên được xử lý giống nhau.

~~~text
Phát sinh lỗi                           Có đủ thông tin để xử lý
----------------------------------------------------------------------
validateOrder  -- InvalidOrder ----->  adapter/API: reject input
calculateQuote -- DomainFailure ---->  nghiệp vụ: từ chối / báo lỗi
saveQuote      -- StorageTimeout --->  transaction/adapter: retry có kiểm soát
saveQuote      -- Conflict --------->  adapter/API: conflict / điều tra
~~~

**Không phải mọi bước đều có quyền quyết định fallback.** Hàm `calculateQuote` không nên trả giá `0` khi database không khả dụng chỉ để pipeline “chạy tiếp”. Ngược lại, adapter REST có thể chọn cách mã hóa một lỗi dữ liệu thành phản hồi 400, trong khi adapter message cần phân loại để không retry vô hạn.

### 2.1. Bốn vị trí thường có thể bắt lỗi

| Vị trí | Ví dụ | Nên chịu trách nhiệm gì? |
|---|---|---|
| **Bên trong một Function** | `try/catch` trong `parseOrder` | Chuyển lỗi thư viện thành lỗi domain có ngữ cảnh, hoặc fallback thật sự hợp lệ |
| **Giữa các bước** | Function kiểm tra hoặc wrapper quanh bước tính | Giữ hợp đồng kiểu, phân biệt lỗi trước/sau xử lý |
| **Bao quanh pipeline** | Service gọi `catalog.lookup(...).apply(...)` | Phân loại lỗi tổng thể, quản lý giao dịch và quyết định có trả/thử lại |
| **Tầng adapter** | HTTP handler, binder, serverless entrypoint | Chuyển lỗi thành response, ack/nack, DLQ, retry nền tảng |

Một lỗi có thể được **bổ sung ngữ cảnh ở tầng thấp** và **quyết định phản hồi ở tầng cao**; không nhất thiết chỉ có đúng một nơi chạm đến exception. Tuy nhiên, nên tránh ghi log cùng stack trace ở mọi tầng rồi gây dữ liệu quan sát trùng lặp.

## 3. Quy tắc đầu tiên: phân loại lỗi trước khi chọn catch

Trước khi viết `catch (Exception e)`, hãy xác định lỗi thuộc nhóm nào.

| Nhóm | Ví dụ | Có thể phục hồi ở đâu? | Retry cùng input? |
|---|---|---|---|
| **Input không hợp lệ** | `quantity=0`, mã đơn sai mẫu | Biên vào hoặc adapter, trả lỗi rõ | Thường không |
| **Quy tắc nghiệp vụ từ chối** | Hàng ngừng bán, vượt hạn mức | Domain/application layer | Thường không nếu không đổi trạng thái/input |
| **Xung đột** | Cùng `orderId` nhưng payload khác | Ranh giới ghi hoặc orchestration | Không retry mù quáng |
| **Hạ tầng tạm thời** | Database connection timeout | Adapter I/O hoặc orchestrator có idempotency | Có thể, với giới hạn/backoff |
| **Lỗi lập trình** | `NullPointerException` không dự kiến | Quan sát và sửa code | Không coi fallback giả là giải pháp |
| **Lỗi chuyển đổi** | JSON không parse, sai content-type | HTTP/broker converter | Thường không với cùng payload |
| **Hủy subscription** | Client ngắt kết nối | Vòng đời reactive/adapter | Không tự xem là lỗi retry nghiệp vụ |

Các nhóm trên là định hướng thiết kế, **không phải mã lỗi Spring Cloud Function mặc định**. Khi triển khai cần định nghĩa rõ policy cho từng nghiệp vụ và adapter.

### 3.1. Hai phép thử để quyết định bắt cục bộ hay truyền lên

Hãy hỏi:

1. **Bước này có biết kết quả thay thế nào vẫn đúng nghiệp vụ không?** Nếu không, không tự tạo fallback.
2. **Bước này có biết trạng thái side effect/transaction không?** Nếu không, không tự kết luận rằng retry sẽ an toàn.

Ví dụ, bước đọc danh mục không bắt buộc có thể dùng dữ liệu cache đã được phê duyệt làm fallback; bước ghi thanh toán không thể “trả thành công” khi không biết transaction đã commit hay chưa.

## 4. Ví dụ xuyên suốt: hợp đồng dữ liệu và ngoại lệ

Bài sử dụng Java 17 và Spring Boot/Spring Cloud Function với mô hình báo giá đơn giản. Các kiểu tường minh giúp quan sát lỗi tại đúng bước.

~~~java
package example.functions;

public final class OrderModels {

    private OrderModels() {}

    public record OrderRequest(String orderId, Integer quantity) {}

    public record ValidatedOrder(String orderId, int quantity) {}

    public record Quote(String orderId, int quantity, long totalVnd) {}
}
~~~

`quantity` dùng `Integer` để biểu diễn cả trường hợp thiếu dữ liệu (`null`). Sau validation, `ValidatedOrder` chứa `int` vì bước đó cam kết số lượng hợp lệ.

Khai báo các ngoại lệ có ý nghĩa:

~~~java
package example.functions;

public final class OrderErrors {

    private OrderErrors() {}

    public static class InvalidOrderException extends RuntimeException {
        public InvalidOrderException(String message) {
            super(message);
        }
    }

    public static class QuoteConflictException extends RuntimeException {
        public QuoteConflictException(String message) {
            super(message);
        }
    }

    public static class QuoteStorageException extends RuntimeException {
        public QuoteStorageException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

Sự khác biệt giữa các lớp giúp tầng gọi chọn hành động. Không dùng một `IllegalStateException` chung cho mọi thứ rồi cố phân loại bằng câu chữ exception.

### 4.1. Port lưu dữ liệu tách khỏi phép tính

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface QuoteStore {
    void save(Quote quote);
}
~~~

Port không tự bảo đảm transaction hay idempotency. Nó chỉ xác định **ranh giới side effect**. Implementation sẽ cần quy tắc ghi và ánh xạ lỗi cụ thể.

## 5. Ba bean: validate, calculate và save

~~~java
package example.functions;

import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.InvalidOrderException;

@Configuration
public class OrderFunctions {

    @Bean
    public Function<OrderRequest, ValidatedOrder> validateOrder() {
        return input -> {
            if (input == null
                    || input.orderId() == null
                    || !input.orderId().matches("ORD-[0-9]+")
                    || input.quantity() == null
                    || input.quantity() < 1
                    || input.quantity() > 100) {
                throw new InvalidOrderException(
                        "OrderRequest khong hop le");
            }

            return new ValidatedOrder(
                    input.orderId(),
                    input.quantity());
        };
    }

    @Bean
    public Function<ValidatedOrder, Quote> calculateQuote() {
        return order -> new Quote(
                order.orderId(),
                order.quantity(),
                Math.multiplyExact(
                        (long) order.quantity(), 125_000L));
    }

    @Bean
    public Consumer<Quote> saveQuote(QuoteStore store) {
        return store::save;
    }
}
~~~

Ba hợp đồng:

~~~text
validateOrder:   OrderRequest → ValidatedOrder
calculateQuote:  ValidatedOrder → Quote
saveQuote:       Quote → void
~~~

Ở đây `validateOrder` và `calculateQuote` không tạo side effect ngoài. `saveQuote` là điểm chạm storage.

Vì `Math.multiplyExact` có thể ném `ArithmeticException` khi tràn số trong bài toán tổng quát, người viết phải cân nhắc giới hạn dữ liệu và lựa chọn kiểu tiền tệ. Với quantity 1..100 cùng đơn giá 125.000 trong ví dụ, giá trị luôn nằm trong khoảng `long`; không nên dùng fallback tùy tiện cho lỗi tính toán không dự kiến.

### 5.1. Implementation in-memory có kiểm tra trùng

Để có thể kiểm thử `saveQuote`, ta dùng kho trong bộ nhớ:

~~~java
package example.functions;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.QuoteConflictException;

@Component
public class InMemoryQuoteStore implements QuoteStore {

    private final ConcurrentHashMap<String, Quote> entries =
            new ConcurrentHashMap<>();

    @Override
    public void save(Quote quote) {
        if (quote == null || quote.orderId() == null) {
            throw new IllegalArgumentException("Quote khong hop le");
        }

        Quote old = entries.putIfAbsent(quote.orderId(), quote);

        if (old != null && !old.equals(quote)) {
            throw new QuoteConflictException(
                    "Cung orderId nhung quote khac");
        }
    }

    public Quote find(String orderId) {
        return entries.get(orderId);
    }

    public int size() {
        return entries.size();
    }

    public Map<String, Quote> snapshot() {
        return Map.copyOf(entries);
    }

    public void clear() {
        entries.clear();
    }
}
~~~

`putIfAbsent` xử lý nguyên tử trong **một JVM**. Đây không phải giải pháp persistence cho nhiều replica: production cần unique constraint/upsert nguyên tử, transaction và chính sách xử lý xung đột tại storage thật.

### 5.2. Ranh giới exception của repository

Khi adapter JDBC/JPA thực hiện `save`, nó có thể nhận exception của thư viện database. Có thể chuyển một lỗi hạ tầng xác định thành `QuoteStorageException` để tầng trên không phụ thuộc chi tiết driver:

~~~java
@Override
public void save(Quote quote) {
    try {
        jdbcRepository.insertIfAbsent(quote);
    } catch (TransientDatabaseFailure ex) {
        throw new QuoteStorageException(
                "Luu Quote that bai tam thoi", ex);
    }
}
~~~

Đây là **mã khái niệm**, cần `jdbcRepository` và `TransientDatabaseFailure` từ adapter cụ thể. Không bắt mọi exception database rồi đổi thành transient: lỗi unique constraint, dữ liệu sai và connection timeout có ý nghĩa khác nhau.

## 6. Ghép imperative: exception đi qua andThen thế nào?

Trong Java, `Function.andThen` nối các lời gọi đồng bộ. Nếu bước thứ nhất ném exception, bước thứ hai **không được gọi**:

~~~java
import java.util.function.Function;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

OrderFunctions definitions = new OrderFunctions();

Function<OrderRequest, ValidatedOrder> validate =
        definitions.validateOrder();
Function<ValidatedOrder, Quote> calculate =
        definitions.calculateQuote();

Function<OrderRequest, Quote> quote =
        validate.andThen(calculate);
~~~

Thử một input không hợp lệ:

~~~java
try {
    Quote result = quote.apply(new OrderRequest("ORD-42", 0));
} catch (OrderErrors.InvalidOrderException ex) {
    System.out.println("Tu choi don hang: " + ex.getMessage());
}
~~~

`validateOrder` ném exception trước khi trả `ValidatedOrder`, nên `calculateQuote` không được gọi.

### 6.1. Bắt bên ngoài pipeline là lựa chọn mặc định tốt

Khi **không có fallback đúng nghiệp vụ trong một bước**, để exception đi qua Function rồi bắt ở service/adapter:

~~~text
validateOrder ── lỗi ──┐
                       |
calculateQuote ── lỗi ─┤
                       v
               Application boundary
                 phân loại exception
                       |
                       v
             HTTP response / nack / retry
~~~

Điều này giữ các Function nhỏ, dễ kiểm thử và không phải biết HTTP status hoặc cấu hình broker.

### 6.2. Bắt cục bộ khi biết cách chuyển đổi lỗi

Một hàm parse có thể chuyển `NumberFormatException` thành lỗi đầu vào rõ ràng:

~~~java
Function<String, Integer> parseQuantity = raw -> {
    try {
        return Integer.parseInt(raw.trim());
    } catch (NumberFormatException ex) {
        throw new OrderErrors.InvalidOrderException(
                "Quantity phai la so nguyen");
    }
};
~~~

Bước parse biết chính xác field nào sai, nên việc đổi lỗi tại đây có lý. Nếu cần giữ nguyên cause để truy vết, hãy cung cấp constructor có `Throwable cause` trong exception domain rồi truyền `ex`; không log stack trace ở đây và log lần nữa ở mọi lớp.

### 6.3. Không catch Exception rồi trả giá trị giả

Tránh:

~~~java
Function<String, Integer> unsafeParse = raw -> {
    try {
        return Integer.parseInt(raw.trim());
    } catch (Exception ignored) {
        return 0;
    }
};
~~~

Nếu `0` có ý nghĩa nghiệp vụ, người gọi sẽ không biết input sai. Ngay cả khi `0` bị validation sau đó từ chối, kiểu lỗi đã bị biến đổi và mất ngữ cảnh gốc. Hãy dùng exception domain hoặc một kiểu `Result<T>` nếu muốn trả lỗi như dữ liệu.

## 7. Dùng catch ở lớp orchestration thay vì trong từng Function

Một service thường là nơi biết yêu cầu có phải *preview* hay *commit* và giao dịch nào đang hoạt động. Nó có thể quyết định có phục hồi bằng dữ liệu đã được kiểm duyệt hay phải truyền lỗi lên adapter.

Ví dụ một lớp orchestration dùng Function imperative:

~~~java
import java.util.function.Function;

Function<OrderModels.OrderRequest, OrderModels.Quote> pipeline =
        definitions.validateOrder()
                   .andThen(definitions.calculateQuote());

try {
    OrderModels.Quote quote = pipeline.apply(
            new OrderModels.OrderRequest("ORD-42", 2));

    // Ứng dụng có thể trả quote hoặc gọi storage riêng.
} catch (OrderErrors.InvalidOrderException ex) {
    // Chuyển thành lỗi input tại boundary.
    throw ex;
}
~~~

Đoạn này chỉ minh họa điểm đặt `catch`; `catch` rồi `throw ex` y nguyên thường **không cần thiết** nếu không bổ sung hành vi hữu ích như metric hoặc ngữ cảnh. Code production nên tránh những catch block không làm gì ngoài chuyển tiếp.

### 7.1. Quy tắc không bắt ở mọi tầng

Một chuỗi `validate → calculate → save` không cần mỗi Function đều:

~~~java
try {
    // Thực hiện việc của bước.
} catch (Exception ex) {
    log.error("Failed", ex);
    throw ex;
}
~~~

Làm vậy khiến cùng một exception bị log nhiều lần, gây nhiễu và có thể lộ dữ liệu. Thay vào đó:

- Bước phát hiện lỗi gắn mã/thông điệp domain phù hợp.
- Ranh giới gọi hoặc adapter phân loại và ghi nhận sự kiện lỗi một cách có cấu trúc.
- Thành phần telemetry có thể đo lỗi theo bước mà không biến lỗi thành một kết quả thành công giả.

## 8. Bắt lỗi trong FunctionCatalog: lookup, apply và downstream

Với Spring Cloud Function, pipeline được phân giải qua tên bean:

~~~java
import java.util.function.Function;
import org.springframework.cloud.function.context.FunctionCatalog;

Function<OrderModels.OrderRequest, OrderModels.Quote> quote =
        catalog.lookup("validateOrder|calculateQuote");

if (quote == null) {
    throw new IllegalStateException("Thieu quote pipeline");
}

OrderModels.Quote output = quote.apply(
        new OrderModels.OrderRequest("ORD-42", 2));
~~~

Ở đây `catalog` là một `FunctionCatalog` đã được Spring inject. Có **hai ranh giới lỗi khác nhau**:

1. **Tra cứu/ghép:** tên không tồn tại, thiếu bean, composition không được hỗ trợ, metadata kiểu không tương thích; lỗi có thể xuất hiện ở `lookup(...)`.
2. **Thực thi:** dữ liệu sai, logic tính lỗi, dependency thất bại; lỗi có thể xuất hiện ở `apply(...)` hoặc ở một tín hiệu reactive khi có Publisher.

Không nên dùng chung một `catch (Exception)` rồi gắn nhãn “input invalid” cho cả hai: lỗi `lookup` thường là lỗi triển khai/cấu hình, không phải lỗi của người gửi dữ liệu.

### 8.1. Chuỗi có Consumer cuối

~~~java
import java.util.function.Consumer;

Consumer<OrderModels.OrderRequest> record = catalog.lookup(
        "validateOrder|calculateQuote|saveQuote");

if (record == null) {
    throw new IllegalStateException("Thieu record pipeline");
}

record.accept(new OrderModels.OrderRequest("ORD-42", 2));
~~~

Tùy phiên bản/adapter Spring Cloud Function, khả năng ghép các dạng `Supplier`/`Function`/`Consumer` phải được xác minh thực tế. Về **hợp đồng dữ liệu**, `Function<OrderRequest,Quote>` rồi `Consumer<Quote>` tạo `Consumer<OrderRequest>`. Consumer trả `void`, nên không thể nối tiếp Function mong nhận output từ nó.

Khi `saveQuote` ném lỗi sau khi database có thể đã commit, một `catch` bên ngoài **không tự biết thao tác ghi đã thành công hay chưa**. Phải thiết kế idempotency ở ranh giới lưu dữ liệu.

## 9. Chọn vị trí bắt lỗi theo mục tiêu xử lý

Xét ba vị trí với cùng chuỗi:

~~~text
A: validateOrder → B: calculateQuote → C: saveQuote
~~~

Có thể xử lý lỗi ở **gần A**, **giữa A và B** hoặc **bao quanh A–C**. Nhưng kết quả có nghĩa khác nhau:

| Vị trí | Điều biết chắc | Điều không biết chắc |
|---|---|---|
| Ngay trong A | Trường nào không hợp lệ | HTTP status/broker ack cụ thể |
| Trong B | Vì sao phép tính không thực hiện được | Người gọi muốn preview hay commit |
| Ngay trong C | Lời gọi storage báo lỗi gì | Database đã commit chưa, nếu mất xác nhận |
| Sau toàn pipeline | Kiểu lỗi được truyền ra và ngữ cảnh request | Có thể không biết trạng thái side effect nếu không tra cứu |
| Adapter ngoài cùng | Giao thức, retry/ack và cách công bố lỗi | Không nên tự viết lại quy tắc nghiệp vụ |

### 9.1. Bắt và biến đổi lỗi tại bước biết rõ nguyên nhân

Ví dụ một parser có quyền dịch lỗi kỹ thuật thành lỗi input:

~~~java
Function<String, Integer> parseQuantity = input -> {
    if (input == null) {
        throw new OrderErrors.InvalidOrderException(
                "Quantity khong duoc null");
    }

    try {
        return Integer.parseInt(input.trim());
    } catch (NumberFormatException ex) {
        throw new OrderErrors.InvalidOrderException(
                "Quantity phai la so nguyen");
    }
};
~~~

Đây là cách **tăng ý nghĩa của lỗi**, không phải che giấu nó. Trong hệ thống thật, nên có mã lỗi ổn định, và nếu cần giữ cause để debug, exception nên hỗ trợ constructor nhận cause.

### 9.2. Bắt ở tầng có quyền chọn fallback

Giả sử hệ thống lấy một **mô tả bổ sung không bắt buộc** từ dịch vụ ngoài. Nếu dịch vụ này tạm thời lỗi, nghiệp vụ vẫn cho phép mô tả rỗng, thì fallback có thể hợp lý:

~~~java
Function<OrderModels.Quote, String> description = quote -> {
    try {
        return optionalDescriptionService.lookup(
                quote.orderId());
    } catch (OptionalDescriptionUnavailableException ex) {
        return "Mo ta chua san sang";
    }
};
~~~

`optionalDescriptionService` và exception trong ví dụ là dependency khái niệm. Fallback chỉ đúng nếu **mô tả thật sự không quan trọng** với nghĩa của báo giá; không áp dụng cách đó cho tổng tiền, quyền truy cập, dữ liệu tài chính hoặc kết quả ghi database.

### 9.3. Truyền lỗi lên nếu không biết cách phục hồi

Nếu `saveQuote` ném `QuoteStorageException`, bước tính toán không có quyền kết luận “đã lưu thành công”. Cách an toàn thường là để lỗi truyền lên một lớp biết retry/transaction/ack, không nuốt lỗi để tạo phản hồi thành công giả.

## 10. Vì sao catch sau side effect nguy hiểm hơn catch trước?

So sánh:

~~~text
Trường hợp A:
  validate -- lỗi --> chưa tới save
  Trạng thái: chưa ghi Quote

Trường hợp B:
  validate → calculate → save -- commit --> network timeout
  Trạng thái: có thể ĐÃ ghi Quote, dù caller thấy lỗi
~~~

Trong trường hợp A, từ chối input thường tương đối đơn giản. Trong trường hợp B, cần xem xét:

- `saveQuote` có transaction/unique constraint hay không?
- Có idempotency key ổn định như `orderId` không?
- Nếu cùng key và payload khác, phải trả conflict hay cập nhật theo phiên bản?
- Adapter có retry lại **cả chuỗi** hay chỉ thao tác lưu?
- Nếu đã phát message sau commit, có nguy cơ gửi trùng hoặc mất sự kiện không?

Không có một catch block nào tự giải quyết được câu hỏi trạng thái commit. **Tính đúng đắn của việc retry đến từ thiết kế storage và giao dịch**, không phải chỉ từ việc bắt exception.

### 10.1. Ví dụ không nên làm

~~~java
Consumer<OrderModels.Quote> unsafeSave = quote -> {
    try {
        store.save(quote);
    } catch (RuntimeException ex) {
        // Sai: adapter co the tuong da thanh cong.
    }
};
~~~

Nếu một consumer/binder xác nhận xử lý thành công sau khi `accept` trả về, việc nuốt lỗi ở đây có thể khiến message không được thử lại dù lưu thất bại. Nên truyền lỗi hoặc có cơ chế ghi trạng thái thất bại bền vững, tùy hợp đồng adapter.

### 10.2. Catch xong lại save lần nữa cũng không mặc định an toàn

~~~java
try {
    store.save(quote);
} catch (OrderErrors.QuoteStorageException ex) {
    store.save(quote); // Chỉ an toàn khi store có hợp đồng idempotent.
}
~~~

Code trên là ví dụ giải thích rủi ro: nếu database đã commit nhưng mất xác nhận, lần thứ hai có thể tạo trùng. Đừng biến một lỗi tạm thời thành thao tác ghi lặp vô giới hạn; cần chính sách retry có giới hạn, backoff và chống trùng.

## 11. Reactor: ngoại lệ trực tiếp khác onError

Spring Cloud Function cũng hỗ trợ Function dùng `Mono` hoặc `Flux`. Với code imperative:

~~~java
Function<OrderModels.OrderRequest, OrderModels.Quote> quoteOne =
        definitions.validateOrder()
                   .andThen(definitions.calculateQuote());

quoteOne.apply(new OrderModels.OrderRequest("ORD-42", 0));
// Throws InvalidOrderException ngay.
~~~

Trong Reactor:

~~~java
import reactor.core.publisher.Mono;

Mono<OrderModels.Quote> quoteMono =
        Mono.just(new OrderModels.OrderRequest("ORD-42", 0))
            .map(quoteOne);
~~~

Tại lúc tạo `quoteMono`, callback `map` thường chưa chạy. Khi có subscription, `quoteOne` được gọi và ngoại lệ từ mapper thường trở thành terminal signal `onError`.

### 11.1. try/catch bao quanh assembly không bắt mọi lỗi reactive

~~~java
try {
    Mono<OrderModels.Quote> result =
            Mono.just(new OrderModels.OrderRequest("ORD-42", 0))
                .map(quoteOne);

    // Chỉ mới tạo Publisher.
} catch (OrderErrors.InvalidOrderException ex) {
    // Thường không vào đây vì mapper còn chưa chạy.
}
~~~

Hãy dùng operator lỗi Reactor hoặc để subscriber/adapter xử lý `onError`.

### 11.2. Lỗi có thể vẫn ném ngay nếu code chạy trước khi tạo Publisher

~~~java
// Sai kỳ vọng: quoteOne.apply được Java gọi ngay.
Mono<OrderModels.Quote> eager =
        Mono.just(quoteOne.apply(
            new OrderModels.OrderRequest("ORD-42", 0)));
~~~

Ở đây exception ném **trước** khi `Mono.just(...)` nhận đối số. Muốn đưa lời gọi vào Publisher:

~~~java
Mono<OrderModels.Quote> deferred =
        Mono.fromCallable(() ->
            quoteOne.apply(
                new OrderModels.OrderRequest("ORD-42", 0)));
~~~

`fromCallable` trì hoãn việc gọi Function đến subscription và chuyển exception thông thường thành `onError`.

### 11.3. Lỗi ở cả hai pha có thể cùng tồn tại

~~~java
Function<OrderModels.OrderRequest,
         Mono<OrderModels.Quote>> quoteReactive = input -> {
    if (input == null) {
        throw new OrderErrors.InvalidOrderException(
                "Input null");
    }

    return Mono.fromCallable(() -> quoteOne.apply(input));
};
~~~

Với `null`, `quoteReactive.apply(null)` ném ngay; với input sai về quantity, `apply` trả Mono nhưng khi subscribe, mapper mới phát lỗi. Chọn ranh giới catch đúng **pha thực thi** chứ không căn cứ vào tên “reactive”.

## 12. Reactor: onErrorResume đặt ngoài hay trong từng phần tử?

Đây là quyết định ảnh hưởng lớn đến pipeline nhận nhiều message. Xét:

~~~java
import reactor.core.publisher.Flux;

Flux<Integer> parsed = Flux.just("2", "bad", "5")
        .map(Integer::parseInt);
~~~

### 12.1. onErrorResume sau toàn Flux

~~~java
Flux<Integer> recovered = Flux.just("2", "bad", "5")
        .map(Integer::parseInt)
        .onErrorResume(
            NumberFormatException.class,
            error -> Flux.just(-1));
~~~

Kết quả:

~~~text
onNext(2)
onNext(-1)
onComplete
~~~

Phần tử `"5"` **không được xử lý tiếp**. `onErrorResume` tại cuối pipeline thay phần chuỗi lỗi bằng Publisher khác, chứ không quay về input tiếp theo.

Vì vậy, cách bắt lỗi này phù hợp khi **toàn bộ nguồn** nên kết thúc hoặc chuyển sang fallback sau lỗi đầu tiên, không phù hợp nếu mỗi event phải được cách ly độc lập.

### 12.2. Xử lý lỗi bên trong từng phần tử

~~~java
import reactor.core.publisher.Mono;

Flux<Integer> validValues = Flux.just("2", "bad", "5")
        .concatMap(raw ->
            Mono.fromCallable(() -> Integer.parseInt(raw))
                .onErrorResume(
                    NumberFormatException.class,
                    error -> Mono.empty()));
~~~

Kết quả:

~~~text
onNext(2)
onNext(5)
onComplete
~~~

Ở đây, catch/`onErrorResume` được đặt **bên trong inner Mono** cho từng input. Phần tử sai không làm mất các phần tử độc lập phía sau. Trong production, không nên âm thầm bỏ `"bad"` nếu nó là một message cần phản hồi, audit, quarantine hoặc đưa vào dead-letter; hãy bổ sung chính sách xử lý dữ liệu sai có quan sát được.

### 12.3. Không dùng onErrorContinue như một catch-all

`onErrorContinue` có ngữ nghĩa phụ thuộc operator và hướng tác động lên upstream, dễ khó đoán khi pipeline có nhiều thành phần. Với xử lý từng event độc lập, ưu tiên mô hình **mỗi input có một inner Publisher** và error handling tại inner, như ví dụ `concatMap`.

### 12.4. Bảng chọn phạm vi xử lý

| Mong muốn | Vị trí xử lý |
|---|---|
| Lỗi một event làm dừng cả stream | `onErrorResume` hoặc để `onError` ở ngoài pipeline |
| Lỗi một event không chặn event khác | `onErrorResume` trong inner Publisher của từng event |
| Biến lỗi kỹ thuật thành lỗi domain | `onErrorMap` gần adapter tạo lỗi, trước tầng phân loại |
| Log/metrics một lỗi mà vẫn lan truyền | `doOnError` tại ranh giới quan sát |
| Retry một thao tác tạm thời, không retry toàn pipeline | `retryWhen` bao đúng Publisher tạo thao tác đó |

## 13. Vị trí onErrorMap và doOnError ảnh hưởng phân loại lỗi

Các operator chạy theo thứ tự bố trí; lỗi đã được phục hồi ở một operator có thể **không còn là lỗi ở các operator phía sau**.

### 13.1. doOnError trước hay sau onErrorResume?

~~~java
Mono<Integer> source =
        Mono.error(new IllegalStateException("temporary"));

Mono<Integer> a = source
        .doOnError(error -> metrics.record(error))
        .onErrorResume(error -> Mono.just(-1));
~~~

`metrics` là dependency minh họa. `doOnError` ở đây quan sát lỗi gốc trước khi fallback được áp dụng.

Nếu đổi thứ tự:

~~~java
Mono<Integer> b = source
        .onErrorResume(error -> Mono.just(-1))
        .doOnError(error -> metrics.record(error));
~~~

`doOnError` phía sau thường **không thấy lỗi gốc** vì `onErrorResume` đã thay nó bằng giá trị và hoàn tất. Điều này không nhất thiết là bug: nó nói rằng nơi đặt phép đo quyết định ta đang đo **lỗi upstream** hay **lỗi còn sót lại sau phục hồi**.

### 13.2. onErrorMap và bộ lọc retry

Nếu một lỗi I/O tạm thời được `onErrorMap` thành exception không còn thông tin transient, `retryWhen` phía sau dùng bộ lọc theo loại gốc có thể không match.

Ví dụ ý tưởng:

~~~text
source -- TemporaryDatabaseError --> onErrorMap(GeneralError)
                                   |
                                   v
                         retryWhen(filter TemporaryDatabaseError)
                         Không còn thấy loại lỗi ban đầu
~~~

Hai phương án:

- Đặt `retryWhen` gần source, **trước** khi đổi loại lỗi; hoặc
- Chuyển sang exception ứng dụng vẫn phân loại được nguyên nhân và giữ cause, rồi để filter nhận diện đúng loại đó.

Không nên quấn mọi exception thành một loại chung rồi áp dụng retry bất kể nguyên nhân.

### 13.3. doOnError không tự phục hồi lỗi

~~~java
Mono<Integer> result = Mono.<Integer>error(
        new IllegalArgumentException("invalid"))
        .doOnError(ex -> System.err.println(ex.getMessage()));
~~~

Downstream vẫn nhận `onError`. `doOnError` chỉ phù hợp cho tác dụng phụ quan sát như logging/metrics, không thay cho `onErrorResume` hoặc handler tại adapter.

## 14. Đặt retryWhen trước hay sau side effect?

Trong Reactor, `retry`/`retryWhen` thường subscribe lại **upstream tính từ vị trí operator**, nên nơi đặt retry quyết định **những công việc nào có thể chạy lại**.

### 14.1. Retry toàn bộ chuỗi có thể ghi lặp

~~~java
Mono<OrderModels.Quote> risky = Mono.fromCallable(
        () -> quoteOne.apply(request))
    .flatMap(quote ->
        persistThenNotify(quote))
    .retryWhen(retryPolicy);
~~~

Trong đoạn mã khái niệm, `request`, `quoteOne`, `persistThenNotify` và `retryPolicy` do ứng dụng cung cấp. Nếu `persistThenNotify` đã lưu database rồi thất bại khi thông báo, retry ở cuối có thể **chạy lại cả phép tính và thao tác lưu**.

Ngay cả khi phép tính thuần, bước lưu chưa chắc an toàn để lặp lại. Không dùng retry cuối chuỗi chỉ vì cú pháp thuận tiện.

### 14.2. Giới hạn retry đúng tại thao tác I/O

Với thao tác `QuoteStore.save` đồng bộ có thể được bao trong Mono:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.retry.Retry;

Mono<Void> saveWithRetry(
        QuoteStore store, OrderModels.Quote quote) {

    return Mono.<Void>fromRunnable(() -> store.save(quote))
            .subscribeOn(Schedulers.boundedElastic())
            .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                    .filter(error ->
                        error instanceof OrderErrors.QuoteStorageException));
}
~~~

Ví dụ phương thức này dùng `boundedElastic` vì port giả định có thể chứa I/O blocking. `Mono.fromRunnable` trì hoãn việc gọi `save` đến subscription; `retryWhen` chỉ bao Publisher lưu dữ liệu. Trong ứng dụng thật cần đặt method vào một lớp và import các kiểu liên quan.

**Cảnh báo:** ngay cả retry chỉ một thao tác `save` cũng có thể gây ghi trùng nếu commit đã thành công nhưng mất xác nhận. Storage cần có idempotency key/unique constraint và phân biệt lỗi transient thật sự. Đừng coi giới hạn phạm vi retry là đủ để đạt exactly-once.

### 14.3. Phân biệt lỗi dữ liệu với lỗi I/O

`InvalidOrderException` không nên được chuyển thành `QuoteStorageException` để vô tình được bộ lọc retry chấp nhận. Lỗi validation phải được phát hiện **trước** khi tạo Publisher lưu dữ liệu, hoặc được truyền nguyên ra ranh giới có quyền từ chối.

## 15. Kiểm soát lỗi khi có Supplier hoặc Consumer

Các tổ hợp khác nhau cho ra hợp đồng lỗi khác nhau:

~~~text
Supplier<OrderRequest> | Function<OrderRequest, Quote>
    ⇒ Supplier<Quote>        (theo hợp đồng composition)

Function<OrderRequest, Quote> | Consumer<Quote>
    ⇒ Consumer<OrderRequest>

Supplier<OrderRequest> | Consumer<OrderRequest>
    ⇒ Runnable
~~~

Về mặt Java thuần, Supplier được gọi qua `get()`, Consumer qua `accept(...)` và Runnable qua `run()`. Khi một bước ném exception trực tiếp, lời gọi bao ngoài có thể quan sát nó; nếu trong Publisher reactive, lỗi có thể đến qua `onError`.

### 15.1. Nguồn Supplier có thể lỗi trước nghiệp vụ

~~~java
import java.util.function.Supplier;

Supplier<OrderModels.OrderRequest> nextOrder =
        () -> queueClient.pollNextOrder();
~~~

`queueClient` là dependency minh họa. Nếu nguồn không đọc được message, validation chưa chạy, nên lỗi này thuộc ranh giới nguồn/transport. Không bắt nó trong `calculateQuote` rồi gán nhãn “đơn hàng sai”.

### 15.2. Consumer có thể đã tạo side effect trước khi lỗi thoát ra

~~~java
Consumer<OrderModels.Quote> sendAndAudit = quote -> {
    store.save(quote);
    auditClient.publish(quote);
};
~~~

Nếu `store.save` thành công nhưng `auditClient.publish` thất bại, retry cả Consumer có thể ghi lại. Hai dependency là ví dụ khái niệm; với nhiều hệ thống, cần transaction/outbox hoặc orchestration có chiến lược khôi phục, không chỉ thêm catch.

### 15.3. Runnable không tự được kích hoạt

Khi `Supplier|Consumer` tạo hành vi `Runnable`, nó không có giá trị kết quả và không tự chạy theo lịch chỉ vì đã có bean composition. Ai gọi `run()` hoặc adapter nào kích hoạt là điều cần xác định. Khả năng ghép/điều phối Supplier và Consumer trong Spring Cloud Function cần kiểm chứng trên phiên bản và adapter thực tế.

## 16. Chọn catch ở boundary không đồng nghĩa nuốt lỗi

Có hai hành vi hoàn toàn khác:

~~~text
Bắt để PHẢN HỒI:
  InvalidOrder -> HTTP 400 / message quarantine / lỗi nghiệp vụ

Bắt để CHE GIẤU:
  Storage failure -> log rồi return success / ack như đã xử lý
~~~

Bắt lỗi là tốt khi nó biến exception thành một **kết quả được định nghĩa rõ** hoặc quyết định một **hành động khôi phục đúng**. Bắt lỗi để làm pipeline trông có vẻ thành công trong khi thực tế thất bại là nguy hiểm.

### 16.1. Lớp application không nên trả boolean chung chung

~~~java
boolean process(OrderModels.OrderRequest request) {
    try {
        recordPipeline.accept(request);
        return true;
    } catch (Exception ignored) {
        return false;
    }
}
~~~

`recordPipeline` là một `Consumer<OrderRequest>` đã được cung cấp. Đoạn code này **mất loại lỗi**: false có thể là input sai, xung đột, timeout hay lỗi lập trình. Nó cũng không cho biết bước ghi có commit chưa.

Nếu ứng dụng cần kết quả thay vì exception, hãy định nghĩa kiểu phản hồi có cấu trúc:

~~~java
enum OutcomeCode {
    ACCEPTED,
    INVALID_INPUT,
    CONFLICT,
    TEMPORARILY_UNAVAILABLE
}

record ProcessingOutcome(
        OutcomeCode code,
        String orderId,
        String message) {}
~~~

Tầng orchestration có thể chuyển **những exception đã phân loại** thành `ProcessingOutcome`, còn những lỗi không dự kiến vẫn được xử lý theo policy chung. Với trạng thái commit chưa rõ, không được đưa ra kết quả “ACCEPTED” nếu chưa có bằng chứng.

## 17. Bảng quyết định nơi bắt lỗi

| Tình huống | Vị trí ưu tiên | Hành động |
|---|---|---|
| `Integer.parseInt` lỗi | Trong parser hoặc DTO validation | Đổi sang lỗi input có ngữ cảnh |
| Quantity không hợp lệ | `validateOrder` phát lỗi; adapter xử lý | Không tính và không ghi |
| SKU đúng mẫu nhưng hết hàng | Domain/application service | Báo nghiệp vụ từ chối; xem concurrency |
| Không có mô tả tùy chọn | Bước enrichment có fallback được phê duyệt | Trả mặc định hợp lệ |
| Tràn số tiền bất ngờ | Domain/application | Báo lỗi/kiểm tra rule, không trả số giả |
| DB transient trước commit | Adapter ghi + orchestrator | Retry giới hạn nếu idempotent |
| Mất kết nối sau commit | Ranh giới transaction/storage | Tra cứu/idempotency; không đoán chưa ghi |
| Lỗi converter JSON | HTTP/message adapter | Từ chối/cách ly trước Function |
| Sai tên bean `lookup` | Khởi động/cấu hình/integration test | Sửa triển khai, không gán lỗi cho client |
| Mapper trong `Flux` lỗi một event | Per-item inner Publisher nếu cần độc lập | Quarantine/fallback theo message |
| Mapper lỗi làm dừng cả stream | Outer `onError` | Dừng luồng và báo lỗi tổng thể |
| Broker giao lại message | Storage/consumer boundary | Dedupe theo event/order ID |

Mỗi quyết định phải nhất quán với việc dữ liệu có thể đến từ HTTP, message hay serverless: **quy tắc domain dùng chung, nhưng chính sách giao thức có thể khác**.

## 18. HTTP: để adapter ánh xạ lỗi domain thành phản hồi

Một REST controller có thể gọi pipeline qua `FunctionCatalog`. Tầng HTTP biết request/response, còn `validateOrder` không cần import bất cứ lớp nào của Spring Web.

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;

@RestController
@RequestMapping("/quotes")
public class QuoteController {

    private final FunctionCatalog catalog;

    public QuoteController(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    @PostMapping
    public Quote preview(@RequestBody OrderRequest request) {
        Function<OrderRequest, Quote> pipeline =
                catalog.lookup("validateOrder|calculateQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Missing quote pipeline");
        }

        return pipeline.apply(request);
    }
}
~~~

`QuoteController` là adapter tùy chỉnh để minh họa. Spring Cloud Function cũng có web adapter riêng tùy starter/phiên bản; không mặc định mọi URL và error handler được tạo giống ví dụ controller này.

### 18.1. Tạo error contract ổn định

~~~java
package example.functions;

public record ApiError(String code, String message) {}
~~~

Ví dụ một `@RestControllerAdvice` phân loại ba loại lỗi domain:

~~~java
package example.functions;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import example.functions.OrderErrors.InvalidOrderException;
import example.functions.OrderErrors.QuoteConflictException;
import example.functions.OrderErrors.QuoteStorageException;

@RestControllerAdvice
public class QuoteErrorHandler {

    @ExceptionHandler(InvalidOrderException.class)
    public ResponseEntity<ApiError> invalid(
            InvalidOrderException ex) {
        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "INVALID_ORDER", ex.getMessage()));
    }

    @ExceptionHandler(QuoteConflictException.class)
    public ResponseEntity<ApiError> conflict(
            QuoteConflictException ex) {
        return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(new ApiError(
                        "ORDER_CONFLICT",
                        "Order da co du lieu khac"));
    }

    @ExceptionHandler(QuoteStorageException.class)
    public ResponseEntity<ApiError> unavailable(
            QuoteStorageException ex) {
        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ApiError(
                        "TEMPORARILY_UNAVAILABLE",
                        "He thong luu tru chua san sang"));
    }
}
~~~

Ở đây, lỗi input thành HTTP 400, conflict thành 409 và một loại lỗi hạ tầng thành 503. Đây là **ví dụ chính sách API**, không phải ánh xạ tự động của Spring Cloud Function. Với API thực tế, phải kiểm tra chi tiết nào an toàn để công khai và thiết kế mã lỗi thống nhất.

### 18.2. Các lỗi xảy ra trước Function cũng phải xử lý

JSON sai cú pháp hoặc không thể chuyển kiểu vào `OrderRequest` có thể thất bại tại converter **trước khi vào controller/Function**. Lúc đó, `InvalidOrderException` chưa được ném. Cần handler riêng cho lỗi deserialize hoặc cơ chế mặc định của Spring Web, tùy yêu cầu API.

Đừng đặt mọi lỗi JSON dưới `validateOrder` rồi suy đoán Function đã chạy. Một lỗi `FunctionCatalog.lookup(...)` sai tên lại là lỗi cấu hình server, không phải 400 do người dùng.

### 18.3. Reactive controller và onError

Một controller WebFlux có thể trả `Mono<Quote>`:

~~~java
@PostMapping("/reactive")
public Mono<OrderModels.Quote> previewReactive(
        @RequestBody OrderModels.OrderRequest request) {

    return Mono.fromCallable(() -> quoteOne.apply(request));
}
~~~

`quoteOne` ở đây là một `Function<OrderRequest,Quote>` được inject, còn method cần đặt trong controller có import `Mono` và các annotation Spring Web thích hợp.

Nếu `quoteOne` ném bên trong Callable, error signal được phát lúc subscription. Exception handler phù hợp với Spring WebFlux vẫn có thể ánh xạ lỗi nếu nó nằm trong vòng đời response mà framework quản lý. Nhưng `try/catch` chỉ bao quanh lệnh `return Mono.fromCallable(...)` thường không bắt được lỗi của Callable.

## 19. Messaging: chọn catch để binder biết xử lý lỗi

Với một function được nối vào Spring Cloud Stream, pipeline có thể được chọn như:

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder|calculateQuote|saveQuote"
~~~

Đầu vào của composition là `OrderRequest`, đầu ra tổng thể là `void`, tương ứng một `Consumer<OrderRequest>` về mặt hợp đồng dữ liệu. Ngoài property này, ứng dụng cần binder, binding/destination, converter và chính sách lỗi phù hợp với hệ thống message.

### 19.1. Không nuốt exception ngay trong Consumer

Giả sử broker cung cấp một `OrderRequest` hợp lệ về cấu trúc nhưng `quantity=0`. Bước `validateOrder` sẽ ném lỗi và `saveQuote` chưa chạy.

Nếu adapter/binder được cấu hình để nhận lỗi và đưa message vào dead-letter hoặc từ chối theo chính sách, việc để lỗi được **phát đúng ra ranh giới consumer** sẽ giúp adapter quyết định. Nếu trong Consumer lại bắt toàn bộ exception rồi im lặng, binder có thể hiểu việc xử lý đã thành công.

Tuy nhiên, không được mặc định “throw là chắc chắn nack” hoặc “onError là chắc chắn DLQ”: các hành vi cụ thể phụ thuộc binder, delivery mode, phiên bản Spring Cloud Stream và chính sách acknowledgement.

### 19.2. Poison message và lỗi tạm thời khác nhau

~~~text
Nhận message
     |
     v
Deserialize ------ sai schema ------> cách ly / DLQ / quan sát
     |
     v
validateOrder ---- quantity = 0 ----> từ chối theo policy
     |
     v
calculateQuote
     |
     v
saveQuote -------- timeout DB ------> retry có giới hạn và idempotency
     |
     v
Ack theo cơ chế binder
~~~

Nếu dữ liệu không hợp lệ cố định, retry cùng payload vô hạn chỉ tạo vòng lặp lỗi. Nếu storage timeout, retry có thể hợp lý nhưng phải chống ghi trùng, đặc biệt khi mất xác nhận sau commit.

### 19.3. Message<T> và xử lý headers

Nếu cần dùng `messageId`, `correlationId` hoặc `schemaVersion`, hãy xác định lớp nào đọc và kiểm tra headers. `Function<Message<OrderRequest>,...>` và `Function<OrderRequest,...>` là hai hợp đồng Java khác nhau.

Một adapter có thể tách payload và context, rồi chuyển thành domain input đủ thông tin. Không nên gán tin cậy cho mọi header do client tự gửi; những trường phục vụ authorization hoặc idempotency phải được kiểm chứng theo nguồn tin cậy.

### 19.4. Lỗi xảy ra sau khi đã xác nhận message

Nếu Consumer tự tạo một subscription bất đồng bộ rồi trả `accept(...)` trước khi công việc hoàn tất, binder có thể không nhận được lỗi ở thời điểm cần quyết định ack. Đây là lý do không nên tự subscribe trong Consumer mà không tuân theo contract adapter; phải kiểm tra rằng **completion và error signal được quan sát ở tầng điều phối message**.

## 20. Serverless: catch ở handler hay bên trong Function?

Một Function có thể được dùng trong serverless handler thông qua adapter phù hợp. Một số nền tảng nhận kết quả đồng bộ; số khác có thể hỗ trợ kiểu kết quả bất đồng bộ. Dù vậy, quy tắc chọn vị trí xử lý lỗi vẫn là:

- **Trong Function domain:** phát hiện và mô tả lỗi nghiệp vụ.
- **Trong handler/adapter:** ánh xạ event vào kiểu input, xử lý lỗi serialization và quyết định phản hồi.
- **Tầng lưu dữ liệu:** transaction, uniqueness/idempotency và trạng thái commit.
- **Nền tảng trigger:** chính sách invocation timeout, retry hoặc dead-letter cụ thể.

Ví dụ một handler Java tùy chỉnh có thể chủ động phân loại:

~~~java
public ProcessingOutcome handle(OrderModels.OrderRequest input) {
    try {
        OrderModels.Quote quote = quotePipeline.apply(input);
        return new ProcessingOutcome(
                OutcomeCode.ACCEPTED, quote.orderId(), "OK");
    } catch (OrderErrors.InvalidOrderException ex) {
        return new ProcessingOutcome(
                OutcomeCode.INVALID_INPUT,
                input == null ? null : input.orderId(),
                "Rejected");
    }
}
~~~

`quotePipeline` là `Function<OrderRequest,Quote>` được cung cấp, còn `OutcomeCode` và `ProcessingOutcome` đã định nghĩa ở mục 16. Đoạn này chỉ minh họa cách xây dựng **kết quả nghiệp vụ có cấu trúc**; trigger serverless thực tế phải chấp nhận kiểu trả về và cơ chế mapping của adapter.

Với hệ thống gọi lại invocation sau timeout, không bắt một `QuoteStorageException` rồi trả `ACCEPTED` chỉ để tránh retry. Cũng không nên trả lỗi tùy tiện nếu nghiệp vụ đã commit thành công mà chưa kiểm tra trạng thái. Chống trùng ở storage vẫn là yêu cầu quan trọng.

## 21. Observability: đo lỗi ở ranh giới, tránh log lặp

Việc chọn vị trí catch có ảnh hưởng đến số lần và chất lượng logging.

~~~text
validateOrder
     |
     v
calculateQuote
     |
     v
saveQuote
     |
     v
Adapter boundary: ghi nhận cuối cùng / phân loại / phản hồi
~~~

Một cách tổ chức:

- Bước domain **ném lỗi có mã hoặc loại rõ ràng**.
- Adapter I/O **đổi lỗi thư viện sang loại hạ tầng** khi có đủ thông tin.
- Ranh giới application/adapter **ghi một sự kiện lỗi được phân loại**.
- Hệ thống tracing/metrics có thể đo lỗi theo từng bước mà không log stack trace lặp lại.

### 21.1. Giữ cause và ngữ cảnh

Khi đổi exception kỹ thuật thành exception ứng dụng, giữ `cause` nếu cần phân tích nguồn gốc:

~~~java
try {
    externalStore.save(quote);
} catch (SomeTransientException ex) {
    throw new OrderErrors.QuoteStorageException(
            "Quote storage unavailable", ex);
}
~~~

`externalStore` và `SomeTransientException` là dependency minh họa cho adapter thật. Không bắt mọi `Exception` rồi gắn nhãn “transient” vì điều đó có thể làm hệ thống retry lỗi dữ liệu hoặc lỗi lập trình.

Nên kèm correlation ID và operation name lấy từ context tin cậy, nhưng không log đầy đủ payload nhạy cảm, mật khẩu hoặc access token. Ở môi trường Reactor có chuyển scheduler, `ThreadLocal` có thể không truyền tự động; cần cơ chế Reactor Context/observability phù hợp.

### 21.2. Đo trước hay sau fallback?

~~~java
Mono<OrderModels.Quote> observed = source
        .doOnError(error -> metrics.incrementFailure())
        .onErrorResume(error -> approvedFallback(error));
~~~

`source`, `metrics` và `approvedFallback` là dependency minh họa. Đặt `doOnError` trước fallback đếm lỗi nguồn; đặt nó sau fallback chỉ đếm lỗi còn sót. Cả hai vị trí đều có thể hợp lệ tùy metric cần đo; điều quan trọng là tên metric phải phản ánh đúng ý nghĩa.

### 21.3. Không nhầm cancellation với error

Khi client hủy subscription hoặc timeout do tầng khác điều khiển, vòng đời có thể xuất hiện **cancel** chứ không phải `onError` tại mọi operator. Nếu cần quan sát các tín hiệu kết thúc, `doFinally(signalType -> ...)` có thể phân biệt `ON_COMPLETE`, `ON_ERROR` và `CANCEL` trong phạm vi Reactor tương ứng.

Không nên gắn mọi cancellation thành lỗi nghiệp vụ cần retry; phải xác định điều gì đã xảy ra với các side effect đang chạy tại thời điểm hủy.

## 22. Khi nào nên dùng Result thay vì exception?

Không phải mọi tình huống không thành công đều là **exception**. Ví dụ việc xác thực dữ liệu người dùng có thể trả một danh sách lỗi mà ứng dụng muốn hiển thị, thay vì lập tức ném exception.

Một kiểu dữ liệu minh họa:

~~~java
import java.util.List;

record ValidationResult<T>(
        T value,
        List<String> errors) {

    boolean valid() {
        return errors != null && errors.isEmpty();
    }
}
~~~

Nếu chọn mô hình này, một Function có thể trả `ValidationResult<ValidatedOrder>`. Bước tiếp theo **không thể giả định** nhận thẳng `ValidatedOrder`; nó phải kiểm tra kết quả rồi chỉ gọi nghiệp vụ khi hợp lệ.

~~~text
OrderRequest
     |
     v
validateOrderAsData
     |
     v
ValidationResult<ValidatedOrder>
     |
     v
routeAcceptedOrRejected
     |
     +-- accepted --> calculateQuote
     |
     +-- rejected --> explicit error result
~~~

Cách này hữu ích khi một yêu cầu cần nhiều lỗi validation hoặc khi trạng thái “từ chối” là kết quả nghiệp vụ dự kiến. Nhưng khi dùng Spring Cloud Function composition tuyến tính, cần thiết kế type trung gian và nhánh xử lý rõ; không coi `Result<T>` là `T`.

### 22.1. Có nên chuyển exception thành HTTP response ngay trong Function?

Thường không nên cho một Function dùng chung nhiều adapter trả `ResponseEntity<?>` chỉ để bắt lỗi. Làm vậy gắn core với HTTP và khiến adapter sự kiện/serverless không thể tái sử dụng tự nhiên.

Tốt hơn là domain tạo **exception hoặc result có ý nghĩa nghiệp vụ**, còn lớp HTTP chuyển thành status/body. Messaging có thể chuyển thành nack/DLQ, còn serverless dùng contract handler của trigger.

## 23. Unit test: lỗi được chặn trước khi ghi

Một bài test tốt cần xác minh hai điều:

1. Lỗi xảy ra với **đúng loại và đúng thời điểm**.
2. Bước có side effect không được gọi nếu input sai.

### 23.1. Test một pipeline imperative

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.InvalidOrderException;

class ImperativeCatchBoundaryTest {

    @Test
    void invalidInputStopsBeforeSave() {
        OrderFunctions definitions = new OrderFunctions();

        Function<OrderRequest, Quote> core =
                definitions.validateOrder()
                           .andThen(definitions.calculateQuote());

        AtomicInteger saveCalls = new AtomicInteger();

        Consumer<Quote> save =
                quote -> saveCalls.incrementAndGet();

        Consumer<OrderRequest> pipeline =
                input -> save.accept(core.apply(input));

        assertThrows(InvalidOrderException.class,
                () -> pipeline.accept(
                    new OrderRequest("ORD-801", 0)));

        assertEquals(0, saveCalls.get());

        pipeline.accept(new OrderRequest("ORD-801", 2));
        assertEquals(1, saveCalls.get());
    }
}
~~~

Ở đây Function validate có trách nhiệm từ chối dữ liệu; `Consumer` chỉ chạy sau khi lõi trả `Quote`. Bằng cách đếm lời gọi, test kiểm tra **ranh giới side effect**, không chỉ kiểm tra exception.

### 23.2. Test lỗi lưu dữ liệu không bị nuốt

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.QuoteStorageException;

class StorageFailureBoundaryTest {

    @Test
    void storageFailurePropagatesToCaller() {
        OrderFunctions definitions = new OrderFunctions();

        Function<OrderRequest, Quote> core =
                definitions.validateOrder()
                           .andThen(definitions.calculateQuote());

        AtomicInteger saveAttempts = new AtomicInteger();

        Consumer<Quote> failingStore = quote -> {
            saveAttempts.incrementAndGet();
            throw new QuoteStorageException(
                    "DB timeout", new IllegalStateException());
        };

        Consumer<OrderRequest> pipeline =
                input -> failingStore.accept(core.apply(input));

        assertThrows(QuoteStorageException.class,
                () -> pipeline.accept(
                    new OrderRequest("ORD-802", 2)));

        assertEquals(1, saveAttempts.get());
    }
}
~~~

Test này chỉ xác nhận **lời gọi lưu đã được thử một lần và lỗi đến được caller**. Nó **không chứng minh** database chưa commit; trong hệ thống thật cần test ở storage/transaction và cơ chế idempotency.

### 23.3. Khi bắt lỗi để đổi loại, test cả cause

Nếu adapter chuyển lỗi database sang `QuoteStorageException`, nên kiểm tra cause ban đầu được giữ và không biến mọi lỗi khác thành lỗi transient.

~~~java
QuoteStorageException ex = assertThrows(
        QuoteStorageException.class,
        () -> failingAdapter.save(quote));

assertNotNull(ex.getCause());
~~~

Trong đoạn này `failingAdapter` là implementation của `QuoteStore` được cấu hình gây lỗi, `quote` là báo giá đầu vào; test cần import `assertThrows` và `assertNotNull`. Code này là mẫu assertion dành cho adapter có cơ chế chuyển loại ngoại lệ thật, không phải lớp `InMemoryQuoteStore` ở mục 5.

## 24. StepVerifier: kiểm tra phạm vi onErrorResume và retry

### 24.1. onErrorResume bên ngoài dừng xử lý nguồn

~~~java
package example.functions;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class OuterErrorBoundaryTest {

    @Test
    void fallbackAtEndDoesNotResumeRemainingSource() {
        Flux<Integer> result =
                Flux.just("2", "bad", "5")
                    .map(Integer::parseInt)
                    .onErrorResume(
                        NumberFormatException.class,
                        error -> Flux.just(-1));

        StepVerifier.create(result)
                .expectNext(2, -1)
                .verifyComplete();
    }
}
~~~

Đúng theo định nghĩa: fallback thay chuỗi lỗi, không quay lại phát `5`.

### 24.2. Bắt lỗi tại mỗi inner Publisher cho phép tiếp tục

~~~java
package example.functions;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class PerItemErrorBoundaryTest {

    @Test
    void badElementDoesNotStopIndependentElements() {
        Flux<Integer> result =
                Flux.just("2", "bad", "5")
                    .concatMap(raw ->
                        Mono.fromCallable(
                            () -> Integer.parseInt(raw))
                            .onErrorResume(
                                NumberFormatException.class,
                                error -> Mono.empty()));

        StepVerifier.create(result)
                .expectNext(2, 5)
                .verifyComplete();
    }
}
~~~

Test xác nhận ranh giới `onErrorResume` nằm trong **từng phần tử**. Khi áp dụng cho broker, không được bỏ qua việc phải quarantine/log/ack message sai theo chính sách.

### 24.3. Retry ngoài side effect có thể gọi lại phần tử đã xử lý

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class RetrySideEffectTest {

    @Test
    void retryResubscribesAndRepeatsEarlierSideEffect() {
        AtomicInteger saves = new AtomicInteger();

        Flux<Integer> result =
                Flux.just("1", "bad", "3")
                    .map(Integer::parseInt)
                    .doOnNext(value -> saves.incrementAndGet())
                    .retry(1);

        StepVerifier.create(result)
                .expectNext(1, 1)
                .expectError(NumberFormatException.class)
                .verify();

        assertEquals(2, saves.get());
    }
}
~~~

`doOnNext` ở test chỉ mô phỏng side effect bằng bộ đếm. Nó giúp chứng minh rằng **vị trí retry** có thể thực thi lại một bước đã chạy thành công ở subscription trước.

### 24.4. Test lỗi trực tiếp khác lỗi reactive

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class EagerVsDeferredTest {

    @Test
    void fromCallableMovesErrorToSubscriber() {
        Function<String, Mono<Integer>> eager =
                input -> Mono.just(Integer.parseInt(input));

        Function<String, Mono<Integer>> deferred =
                input -> Mono.fromCallable(
                    () -> Integer.parseInt(input));

        assertThrows(NumberFormatException.class,
                () -> eager.apply("bad"));

        Mono<Integer> result = assertDoesNotThrow(
                () -> deferred.apply("bad"));

        StepVerifier.create(result)
                .expectError(NumberFormatException.class)
                .verify();
    }
}
~~~

Test này cho thấy `try/catch` hoặc `assertThrows` quanh `apply` không thay thế `StepVerifier` khi công việc được trì hoãn đến subscription.

## 25. Integration test FunctionCatalog và boundary

Các unit test trước đó không kiểm tra Spring đã đăng ký đúng bean hay chưa. Tạo một lớp Spring Boot cùng package `example.functions`:

~~~java
package example.functions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Trong ứng dụng có `OrderFunctions`, `InMemoryQuoteStore`, Spring Cloud Function context và Spring Boot Test tương thích, có thể test:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.InvalidOrderException;

@SpringBootTest(classes = OrderApplication.class)
class OrderCatalogBoundaryTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    InMemoryQuoteStore store;

    @Test
    void validQuoteIsCalculatedByName() {
        Function<OrderRequest, Quote> pipeline =
                catalog.lookup("validateOrder|calculateQuote");

        assertNotNull(pipeline);

        assertEquals(
                new Quote("ORD-901", 2, 250_000L),
                pipeline.apply(new OrderRequest("ORD-901", 2)));
    }

    @Test
    void invalidInputCannotReachConsumer() {
        Consumer<OrderRequest> pipeline =
                catalog.lookup(
                    "validateOrder|calculateQuote|saveQuote");

        assertNotNull(pipeline);

        assertThrows(InvalidOrderException.class,
                () -> pipeline.accept(
                    new OrderRequest("ORD-902", 0)));

        assertNull(store.find("ORD-902"));
    }

    @Test
    void repeatedValidInputDoesNotCreateTwoEntries() {
        Consumer<OrderRequest> pipeline =
                catalog.lookup(
                    "validateOrder|calculateQuote|saveQuote");

        assertNotNull(pipeline);

        OrderRequest request = new OrderRequest("ORD-903", 2);

        pipeline.accept(request);
        pipeline.accept(request);

        assertEquals(
                new Quote("ORD-903", 2, 250_000L),
                store.find("ORD-903"));
    }
}
~~~

Test này xác minh cấu hình tên và side effect trong JVM. **Nó không chứng minh storage nhiều instance có transaction bền vững** và không kiểm tra binding/HTTP adapter thực tế. Dùng khóa khác nhau giúp tránh một số đụng độ giữa test; với test chạy song song và context dùng chung, vẫn cần isolation hoặc reset phù hợp.

### 25.1. Negative test cho lỗi khi lookup

Một biểu thức tên sai có thể bị framework từ chối ở thời điểm tra cứu hoặc khi thực thi, tùy phiên bản và cơ chế wrapper. Không nên hard-code rằng mọi biểu thức sai chắc chắn trả `null`. Test cần dựa vào contract của version đang chạy và kiểm tra **không tạo side effect ngoài ý muốn**.

### 25.2. Kiểm thử adapter vẫn là một tầng riêng

| Tầng test | Điều xác minh |
|---|---|
| Unit `Function` | Lỗi input/quy tắc được phát đúng |
| Unit `QuoteStore` | Conflict, idempotency, đổi loại exception |
| Unit Reactor | `onErrorResume` ở đúng phạm vi, retry có thể lặp |
| Spring context/catalog | Đăng ký bean, ghép tên, kiểu input/output |
| HTTP adapter | Body, status, error handler, timeout |
| Message binder | Converter, ack/nack, retry/DLQ, redelivery |
| Serverless handler | Event mapping, invocation timeout/retry |
| Fault-injection/storage thật | Commit không rõ, race condition, uniqueness |

Một bài test catalog thành công không chứng minh adapter đã subscribe Publisher hoặc đã map lỗi thành status/nack đúng.

## 26. Checklist chọn nơi xử lý lỗi

Trước khi hoàn tất một pipeline Spring Cloud Function, hãy trả lời:

1. **Lỗi xuất hiện tại bước nào?** Converter, validation, Function, Consumer hay adapter?
2. **Nó xuất hiện lúc nào?** `lookup`, `apply`, assembly, subscription hay sau commit?
3. **Nơi định bắt có thông tin để phục hồi đúng không?** Có fallback được phê duyệt?
4. **Lỗi thuộc nhóm nào?** Input, domain rejection, conflict, transient I/O hay programming error?
5. **Nếu bỏ qua lỗi, nghiệp vụ có bị báo thành công giả không?**
6. **Nếu retry, thao tác nào sẽ chạy lại?** Cả chain, một inner Publisher hay chỉ storage call?
7. **Có side effect nào đã chạy trước lỗi không?** Có transaction, idempotency key và uniqueness?
8. **Có cần xử lý riêng từng phần tử không?** Hay một lỗi phải dừng toàn bộ Flux?
9. **Error signal có tới được adapter không?** Ai subscribe Publisher?
10. **Adapter sẽ làm gì?** HTTP status, ack/nack, DLQ hay serverless retry?
11. **Lỗi có được log/metric đúng một cách hữu ích không?** Có giữ cause/correlation ID?
12. **Test đã xác minh cả lỗi lẫn việc không tạo side effect sai chưa?**

Một cách thực hành hữu ích là vẽ pipeline và đánh dấu **dòng dữ liệu**, **điểm phát lỗi**, **điểm commit**, **điểm retry** và **điểm trả lời** trước khi viết catch hoặc operator Reactor.

## 27. Bài tập thực hành

**Bài 1 — Bắt lỗi parse.** Cho `parseQuantity: Function<String,Integer>`. Khi `Integer.parseInt` ném `NumberFormatException`, nên đổi thành `InvalidOrderException` ở đâu để giữ thông tin field?

**Bài 2 — Catch trước side effect.** Cho `validateOrder → calculateQuote → saveQuote`. Với quantity bằng `0`, bước nào phát lỗi? Vì sao test phải kiểm tra `saveQuote` không được gọi?

**Bài 3 — Ghi rồi timeout.** `saveQuote` đã commit nhưng mất xác nhận. Tầng application bắt `QuoteStorageException`. Có thể trả “chưa ghi” ngay không? Cần thêm cơ chế gì?

**Bài 4 — onErrorResume toàn Flux.** Cho `Flux.just("2","bad","5").map(Integer::parseInt).onErrorResume(ex -> Flux.just(-1))`. Kết quả là gì? Vì sao `5` không còn?

**Bài 5 — Lỗi theo từng message.** Viết một pipeline có `concatMap` và `Mono.fromCallable` để phần tử `"bad"` không chặn `"5"`. Vì sao production không được im lặng bỏ message?

**Bài 6 — doOnError trước hay sau fallback?** Nếu muốn đếm lỗi nguồn đã được phục hồi, đặt `doOnError` ở vị trí nào so với `onErrorResume`? Nếu muốn đếm lỗi chưa phục hồi thì sao?

**Bài 7 — Bộ lọc retry.** Một adapter chuyển `TemporaryDatabaseException` thành `ApplicationException` trước `retryWhen`. Bộ lọc đang tìm loại cũ sẽ gặp vấn đề gì? Hãy đề xuất thay đổi.

**Bài 8 — Ranh giới retry.** Một pipeline tính Quote, ghi DB rồi phát sự kiện. `retryWhen` ở cuối có thể chạy lại những bước nào? Hãy nêu cách bảo vệ khi commit đã xảy ra.

**Bài 9 — Adapter.** Cùng `InvalidOrderException` xuất hiện qua HTTP và Kafka. Vì sao không nên để `validateOrder` tự dựng `ResponseEntity` hoặc gọi DLQ trực tiếp?

**Bài 10 — FunctionCatalog.** Pipeline `"validateOrder|calculateQuote|saveQuote"` có hợp đồng tổng thể gì? Nếu `lookup` sai tên, đó có phải lỗi input của người dùng không?

**Bài 11 — Test.** Viết ít nhất một `assertThrows` cho Function imperative và một `StepVerifier.expectError` cho mapper reactive. Điều gì phải được kiểm tra thêm nếu pipeline có Consumer ghi database?

**Bài 12 — Serverless.** Handler timeout sau khi storage commit. Nền tảng gửi lại invocation. Bắt exception ở handler có ngăn được ghi trùng không? Thiết kế idempotency ra sao?

### Gợi ý đáp án

- **Bài 1:** Bắt tại parser để đổi sang lỗi domain có thông tin `quantity`, sau đó để adapter quyết định phản hồi.
- **Bài 2:** `validateOrder` ném lỗi; kiểm tra số lần `saveQuote` gọi bằng 0 để phát hiện thứ tự sai hoặc side effect ẩn.
- **Bài 3:** Không. Trạng thái commit có thể đã thành công; cần tra cứu theo idempotency key hoặc retry an toàn qua uniqueness/transaction.
- **Bài 4:** Phát `2` rồi `-1` rồi complete; `onErrorResume` thay phần luồng sau lỗi.
- **Bài 5:** Đặt `onErrorResume` trong inner Mono, kết hợp quarantine/DLQ/metrics thay vì bỏ lỗi lặng lẽ.
- **Bài 6:** Đo lỗi nguồn ở trước `onErrorResume`; đo lỗi chưa được phục hồi ở sau.
- **Bài 7:** Filter có thể không match; đặt retry trước bước chuyển loại hoặc giữ loại/cause có thể nhận diện.
- **Bài 8:** Retry cuối có thể subscribe lại cả quá trình; cần idempotency ở storage và outbox hoặc cơ chế nhất quán nếu publish event.
- **Bài 9:** Domain không nên phụ thuộc transport; HTTP trả status/body còn binder áp dụng ack/retry/DLQ riêng.
- **Bài 10:** `Consumer<OrderRequest>`; lỗi lookup sai tên thường thuộc cấu hình/triển khai, không phải lỗi client.
- **Bài 11:** Test direct throw và `onError` khác pha; với Consumer cần assert side effect không xảy ra khi validation sai, và idempotency khi retry.
- **Bài 12:** Catch không đủ; dùng key ổn định, storage ghi nguyên tử/unique, phát hiện xung đột và chính sách retry rõ.

## 28. Ghi nhớ

- **Bắt lỗi ở nơi có đủ thông tin để quyết định đúng**, không mặc định ở mọi Function.
- Parser/validator có thể chuyển lỗi kỹ thuật thành lỗi domain; business core không cần biết HTTP status hoặc DLQ.
- Với Java imperative, exception thường truyền trực tiếp qua `andThen` đến `apply`/`accept`; với Reactor, lỗi trong mapper thường xuất hiện qua `onError` lúc subscription.
- `onErrorResume` sau toàn Flux thay luồng khi lỗi; xử lý từng message cần error boundary trong inner Publisher.
- `doOnError` chỉ quan sát, `onErrorMap` đổi loại lỗi, `retryWhen` subscribe lại upstream; **vị trí operator quyết định phạm vi tác động**.
- Không dùng fallback giả, `catch (Exception)` nuốt lỗi hoặc retry sau commit mà không có idempotency.
- `FunctionCatalog` và `spring.cloud.function.definition` giúp ghép/chọn logic, **không tự cung cấp retry, transaction, HTTP error mapping hay binder acknowledgement**.
- Độ tin cậy cần kiểm thử theo nhiều tầng: Function, storage/side effect, Reactor, catalog và adapter HTTP/sự kiện/serverless.



