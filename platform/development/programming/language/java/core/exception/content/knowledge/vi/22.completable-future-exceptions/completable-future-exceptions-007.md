# whenComplete: quan sát kết quả và các lỗi phát sinh khi quan sát

## 1. Mục tiêu và ý nghĩa trong Java CompletableFuture

`CompletableFuture<T>` biểu diễn một kết quả có thể chưa sẵn sàng, hoàn thành thành công hoặc hoàn thành ngoại lệ. Khi thiết kế một chuỗi bất đồng bộ, ta thường muốn **quan sát** kết quả ở một điểm nào đó để ghi log, ghi metric, phát tín hiệu chẩn đoán hoặc dọn ngữ cảnh, trong khi vẫn giữ nguyên kết quả tính toán chính.

`whenComplete((value, error) -> { ... })` cung cấp chính xác một điểm quan sát cả hai nhánh:

- Khi stage nguồn hoàn thành bình thường, callback nhận `value` và `error == null`.
- Khi stage nguồn hoàn thành ngoại lệ, callback nhận `error` khác `null`; `value` không chứa kết quả thành công.
- Callback trả về `void`: nó không phải một hàm biến đổi `T` thành kiểu khác và không mặc định biến lỗi thành thành công.
- Bản thân lời gọi `whenComplete` trả về một **CompletionStage/CompletableFuture mới** đại diện cho việc quan sát xong. Nếu action quan sát **cũng ném exception**, trạng thái của stage mới tuân theo quy tắc ưu tiên lỗi được giải thích ở phần dưới.

Cần đặc biệt phân biệt hai loại thất bại: **lỗi từ công việc nguồn** và **lỗi phát sinh trong chính callback quan sát**. Nếu bỏ qua sự khác biệt này, ứng dụng có thể gán nhầm lỗi ghi metric thành lỗi nghiệp vụ, hoặc mất thông tin lỗi phụ khi nguồn và observer cùng thất bại.

Sau bài này, bạn có thể đọc đúng hợp đồng `whenComplete` trong Java 17+, biết sự khác nhau giữa `whenComplete`, `handle`, `exceptionally`; xác định lỗi nào được giữ khi observer ném exception; viết ví dụ runnable và tổ chức việc ghi nhận lỗi an toàn.

## 2. Chữ ký và hai tham số của callback

Kiểu khai báo cốt lõi theo API là:

~~~java
CompletionStage<T> whenComplete(
        BiConsumer<? super T, ? super Throwable> action);
~~~

Đây là **chữ ký minh họa trích ý nghĩa của giao diện `CompletionStage<T>`**, không phải khai báo chương trình độc lập. Khi sử dụng `CompletableFuture<T>`, phương thức tương ứng trả `CompletableFuture<T>`. `BiConsumer` là một callback nhận **hai tham số và không trả giá trị**.

Một biểu thức sử dụng phổ biến:

~~~java
CompletableFuture<String> observed = source.whenComplete((value, error) -> {
    if (error == null) {
        System.out.println("result = " + value);
    } else {
        System.err.println("failed: " + error);
    }
});
~~~

Đây là fragment, giả định `source` là `CompletableFuture<String>` và các import tương ứng đã có. `observed` là stage **mới**. Nó không phải chính `source`, mặc dù mang cùng kiểu giá trị String. Thực tế có thể có nhiều stage quan sát cùng một nguồn, và thứ tự callback khác nhau không nên bị giả định nếu không thiết lập quan hệ phụ thuộc.

### 2.1. Ý nghĩa chính xác của `value` và `error`

| Nguồn hoàn thành | `value` trong callback | `error` trong callback | Điều cần hiểu |
| --- | --- | --- | --- |
| `complete("OK")` | `"OK"` | `null` | Nguồn thành công có giá trị |
| `complete(null)` | `null` | `null` | Nguồn **vẫn thành công** với giá trị `null` |
| `completeExceptionally(exception)` | Thông thường `null` | `Throwable` liên quan lỗi | Nguồn hoàn thành ngoại lệ |
| `cancel(...)` thành công | Không có kết quả bình thường | Lỗi hủy/đại diện cho completion ngoại lệ | Cancellation cũng là một dạng hoàn thành ngoại lệ để observer nhận biết |

**Chỉ dùng `error == null` làm dấu hiệu thành công**. Không dùng `value != null`, vì `CompletableFuture<Void>` hoặc một stage trả `null` hợp lệ sẽ hoàn thành thành công với `value == null`.

`Throwable error` có thể là ngoại lệ gốc hoặc một `CompletionException` bọc ngoại lệ gốc, tùy cách nguồn/stage trước được hoàn thành. Khi muốn thống kê loại lỗi, hãy xử lý wrapper đúng hợp đồng và xem chuỗi `cause` thay vì so chuỗi văn bản của `getMessage()`. Không gọi `error.getCause().getMessage()` khi chưa kiểm tra `error` và `getCause()` có khác `null` hay không.

## 3. Quy tắc nền tảng: callback quan sát và stage phụ thuộc

Hãy xét:

~~~text
CompletionStage<T> source
          |
          +--- whenComplete(action) ---> CompletionStage<T> observed
                                         |
                                         +--- join()/get()/stage tiếp
~~~

Stage `observed` chỉ hoàn tất sau khi `source` đã hoàn thành và action `whenComplete` đã thực hiện hoặc thất bại theo cơ chế completion. Do đó, nếu bạn cần bảo đảm observer đã chạy xong **trước khi thực hiện bước tiếp theo**, hãy đợi/chain **`observed`**, chứ không chỉ `source`.

Lời gọi `source.join()` có thể hoàn thành trước khi một callback bất đồng bộ `whenCompleteAsync` kịp chạy. Ngay cả với callback dạng đồng bộ `whenComplete`, khi nhiều thread cạnh tranh thực thi completion và phụ thuộc, không nên dựa vào một lịch chạy tình cờ. Các thao tác tương tác cần có quan hệ phụ thuộc rõ ràng.

`whenComplete` không tự tạo một “sổ nhật ký đáng tin cậy” về trạng thái hệ thống. Nó chỉ cung cấp một điểm chạy mã Java trong vòng đời stage. Nếu tiến trình dừng hoặc lỗi ghi log xảy ra, không có bảo đảm tất cả sự kiện đã được lưu bền vững.

## 4. Khi observer chạy bình thường: kết quả và lỗi nguồn được giữ nguyên

Nếu callback `whenComplete` hoàn tất bình thường (không ném exception):

- Nguồn **thành công**: stage trả về cũng hoàn thành bình thường với **cùng giá trị `T`**.
- Nguồn **thất bại**: stage trả về vẫn hoàn thành ngoại lệ, phản ánh lỗi từ nguồn.
- Nguồn **bị hủy**: action có thể nhận thông tin lỗi hủy; stage phụ thuộc vẫn mang trạng thái ngoại lệ tương ứng. Không mặc định stage phụ thuộc có cùng cờ `isCancelled()` với nguồn; việc quan sát hủy và kiểu exception có thể khác theo tầng bọc.

Ví dụ fragment:

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("saved");

CompletableFuture<String> observed =
        source.whenComplete((value, error) ->
                System.out.println("observer saw: " + value));

System.out.println(observed.join());
~~~

Đây là đoạn minh họa có thể đặt trong `main` sau khi import `java.util.concurrent.CompletableFuture`. Với `source` đã hoàn thành thành công và callback không ném lỗi, output là:

~~~text
observer saw: saved
saved
~~~

Giá trị `saved` không được tạo ra bởi `whenComplete`; nó đến từ `source`. Callback chỉ quan sát. Nếu muốn **thay** kết quả, chọn `thenApply` hoặc `handle` tùy yêu cầu, thay vì cố trả một String từ lambda `whenComplete` (vốn yêu cầu hành vi `void`).

## 5. Khi observer ném exception: quy tắc ưu tiên quan trọng nhất

Hợp đồng của `CompletionStage.whenComplete` quy định: **nếu action được cung cấp ném exception, stage kết quả hoàn thành ngoại lệ bằng lỗi từ action, trừ khi stage nguồn vốn đã hoàn thành ngoại lệ; trong trường hợp nguồn đã thất bại, lỗi nguồn được ưu tiên**.

Đây là trọng tâm của chủ đề. Có bốn trường hợp:

| Nguồn trước callback | Action quan sát | Kết cục của stage `whenComplete` trả về |
| --- | --- | --- |
| Thành công | Thành công | Thành công với giá trị nguồn |
| Thành công | **Ném exception B** | **Thất bại bởi B** |
| **Thất bại bởi A** | Thành công | **Thất bại bởi A** |
| **Thất bại bởi A** | **Ném exception B** | **Thất bại bởi A (ưu tiên lỗi nguồn)** |

Quy tắc ưu tiên này tránh việc observer thay thế lỗi chính A khi chính công việc nguồn đã thất bại. Nhưng bạn **không nên trông chờ** Java tự ghi log, bảo quản nguyên nhân B như `suppressed exception`, hoặc tự gửi sự kiện về B ở mọi triển khai. Nếu thông tin “observer cũng lỗi” có giá trị, hãy ghi nhận B bằng một đường quan sát riêng, rõ ràng và an toàn.

### 5.1. Nguồn thành công nhưng observer lỗi

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("OK");

CompletableFuture<String> observed = source.whenComplete((value, error) -> {
    throw new IllegalArgumentException("metric sink failed");
});
~~~

Đây là fragment có import `CompletableFuture` và chưa có mã bắt exception. Khi gọi `observed.join()`, caller nhận `CompletionException` với cause tương ứng `IllegalArgumentException`. Tuy nhiên `source.join()` vẫn trả `"OK"`: tính toán nguồn **đã thành công**, chính nhánh quan sát phụ làm stage mới thất bại.

Đây là lý do không nên gắn một callback metrics có thể ném exception rồi gọi `observed.join()` để xác nhận nghiệp vụ đã hoàn thành: hệ thống có thể báo thao tác thất bại **chỉ vì logging/metrics thất bại**, dù tác vụ chính đã thành công. Có khi đây là chính sách phù hợp (audit bắt buộc), nhưng phải do hợp đồng quyết định.

### 5.2. Nguồn đã thất bại và observer cũng lỗi

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
source.completeExceptionally(new IllegalStateException("load failed"));

CompletableFuture<String> observed = source.whenComplete((value, error) -> {
    throw new IllegalArgumentException("metric sink failed");
});
~~~

Fragment này tạo một nguồn thất bại trước. Khi caller gọi `observed.join()`, lỗi nguồn `IllegalStateException("load failed")` giữ ưu tiên, còn lỗi từ observer không thay thế kết cục chính.

Điều này **không có nghĩa observer không chạy**: action vẫn được gọi và vẫn có thể ném lỗi; chỉ là exception B không trở thành nguyên nhân chính của `observed`. Đừng coi dòng log của A là bằng chứng hệ thống metrics không gặp sự cố. Nếu phải đảm bảo sự cố quan sát được báo cáo, cần kênh giám sát riêng hoặc logic bắt B tường minh.

### 5.3. Vì sao `source` và `observed` cần được phân biệt?

`whenComplete` không sửa lại trạng thái terminal của `source`. Nó tạo stage phụ thuộc với trạng thái có thể **khác** nguồn khi observer lỗi. Những nơi chỉ quan sát `source` sẽ thấy success; những nơi quan sát `observed` có thể thấy failure. Vì vậy, khi viết API, hãy quyết định caller có thực sự cần coi hoạt động quan sát là điều kiện để công việc được công nhận thành công hay không.

## 6. Ví dụ Java 17 đầy đủ, biên dịch/chạy được

Chương trình sau kiểm chứng năm tình huống:
1. Nguồn thành công và observer chỉ in kết quả.
2. Nguồn thất bại, observer đọc loại exception.
3. Nguồn thành công nhưng observer ném exception.
4. Nguồn thất bại **và** observer ném exception khác: lỗi nguồn vẫn giữ ưu tiên.
5. Ghép `whenComplete` với `exceptionally` để ghi nhận rồi chủ động biến lỗi thành một giá trị dự phòng.

Lưu thành **`WhenCompleteObservationDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class WhenCompleteObservationDemo {
    static String messageOf(CompletableFuture<?> future) {
        try {
            future.join();
            return "SUCCESS";
        } catch (CompletionException ex) {
            Throwable cause = ex.getCause();
            return cause.getClass().getSimpleName() + ": " + cause.getMessage();
        }
    }

    public static void main(String[] args) {
        CompletableFuture<String> success = CompletableFuture.completedFuture("OK");
        CompletableFuture<String> watchedSuccess = success.whenComplete((value, error) -> {
            System.out.println("observe success: " + value + ", error=" + error);
        });
        System.out.println("result: " + watchedSuccess.join());

        CompletableFuture<String> failed = new CompletableFuture<>();
        failed.completeExceptionally(new IllegalStateException("load failed"));
        CompletableFuture<String> watchedFailure = failed.whenComplete((value, error) -> {
            System.out.println("observe failure: " + error.getClass().getSimpleName());
        });
        System.out.println("source failure: " + messageOf(watchedFailure));

        CompletableFuture<String> badObserver = success.whenComplete((value, error) -> {
            throw new IllegalArgumentException("metrics failed");
        });
        System.out.println("observer failure: " + messageOf(badObserver));
        System.out.println("original success: " + success.join());

        CompletableFuture<String> bothFail = failed.whenComplete((value, error) -> {
            throw new IllegalArgumentException("observer also failed");
        });
        System.out.println("primary failure: " + messageOf(bothFail));

        CompletableFuture<String> recovered = failed
                .whenComplete((value, error) -> System.out.println("logged failure"))
                .exceptionally(error -> "fallback");
        System.out.println("recovered: " + recovered.join());
    }
}
~~~

Từ thư mục chứa file với JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 WhenCompleteObservationDemo.java
java WhenCompleteObservationDemo
~~~

Stdout chính xác:

~~~text
observe success: OK, error=null
result: OK
observe failure: IllegalStateException
source failure: IllegalStateException: load failed
observer failure: IllegalArgumentException: metrics failed
original success: OK
primary failure: IllegalStateException: load failed
logged failure
recovered: fallback
~~~

### 6.1. Phân tích kết quả theo từng mốc

- Hai dòng đầu: `watchedSuccess` trả lại chuỗi `OK` từ nguồn. `error=null` thể hiện nguồn thành công.
- Hai dòng tiếp: `failed` là nguồn đã được `completeExceptionally` với `IllegalStateException`. `whenComplete` đọc loại lỗi và stage mới vẫn thất bại với lỗi nguồn.
- Dòng `observer failure`: nguồn `success` vẫn thành công, nhưng `badObserver` thất bại do action ném `IllegalArgumentException`.
- Dòng `original success`: chính source `success` vẫn trả `OK`, chứng minh observer không quay ngược trạng thái nguồn.
- Dòng `primary failure`: action của `bothFail` cũng ném, nhưng failure gốc `load failed` giữ quyền ưu tiên theo hợp đồng.
- Hai dòng cuối: `whenComplete` ghi nhận thất bại, sau đó stage `exceptionally` nhận lỗi và trả `fallback`; đây là **chuyển đổi recovery có chủ đích**, không phải một tính năng tự động của `whenComplete`.

Các source trong chương trình đều hoàn thành **trước khi** đăng ký observer, vì vậy callback không có cạnh tranh giữa nhiều worker và stdout đã được định nghĩa rõ. Trong một hệ thống thật đang chạy bất đồng bộ, thứ tự in log của nhiều stage độc lập có thể không xác định nếu không có quan hệ phụ thuộc/chờ thích hợp.

Phương thức `messageOf` minh họa trường hợp future chắc chắn hoàn thành bằng `CompletionException` trên `join()`. Trong thư viện production, cần cân nhắc cả `CancellationException` và những loại lỗi khác; `getCause()` cũng nên được kiểm tra an toàn nếu nguồn lỗi không tuân theo giả định của helper. Không sao chép helper này thành mã xử lý mọi loại throwable của ứng dụng mà không bổ sung policy.

## 7. `whenComplete` khác gì `handle` và `exceptionally`?

Sự khác biệt nằm ở **mục đích của callback và kiểu trả về**:

| API | Callback nhận gì? | Có chủ đích tạo giá trị mới? | Hành vi khi nguồn thất bại |
| --- | --- | --- | --- |
| `thenApply(fn)` | Chỉ giá trị `T` khi thành công | Có, `T -> U` | Thường bỏ qua `fn` và truyền failure |
| `exceptionally(fn)` | `Throwable` khi nguồn lỗi | Có, thay bằng giá trị `T` | Có thể phục hồi bằng giá trị do `fn` trả |
| `handle(fn)` | `T` và `Throwable` | Có, tạo `U` ở cả hai nhánh | Có thể phân loại hoặc phục hồi lỗi thành giá trị |
| `whenComplete(action)` | `T` và `Throwable` | **Không**, action trả `void` | Giữ failure nguồn nếu action không ném; nếu cả hai cùng lỗi thì nguồn ưu tiên |
| `whenCompleteAsync(action, executor)` | Như `whenComplete` | Không | Cùng ngữ nghĩa failure, nhưng action được lên lịch bất đồng bộ |

### 7.1. Khi nào dùng `handle`?

Nếu muốn chuyển success/failure thành một `Result` có kiểu:

~~~java
CompletableFuture<Outcome> mapped = source.handle((value, error) -> {
    if (error == null) {
        return new Succeeded(value);
    }
    return new Failed(error);
});
~~~

Đây là fragment minh họa, giả định `source` có kiểu phù hợp và `Outcome`, `Succeeded`, `Failed` đã được định nghĩa. `handle` được phép trả một đối tượng có kiểu mới cho cả thành công lẫn thất bại. `whenComplete` lại không có đường return dữ liệu như vậy.

Nếu callback `handle` tự ném exception, stage của `handle` có thể thất bại bởi exception đó, kể cả khi nguồn đã lỗi; **không áp dụng quy tắc ưu tiên lỗi nguồn của `whenComplete` cho `handle` một cách máy móc**. Đây là một khác biệt quan trọng khi phân tích lỗi phát sinh trong observer.

### 7.2. Khi nào dùng `exceptionally`?

Nếu caller muốn cung cấp fallback khi nguồn gặp lỗi:

~~~java
CompletableFuture<String> fallback = source.exceptionally(error -> {
    return "cache value";
});
~~~

Đây là fragment giả định `source` là `CompletableFuture<String>`. Kết quả mới có thể hoàn thành bình thường dù nguồn thất bại. Chính sách fallback phải đúng nghiệp vụ: một thao tác tạo thanh toán không thể tùy tiện biến lỗi truyền tiền thành “đã thành công”.

### 7.3. Khi nào dùng `whenComplete`?

Khi bạn muốn **quan sát** mà không định nghĩa lại kết quả:
- Ghi log thành công/thất bại và mã tác vụ.
- Ghi metric, phân loại latency hoặc error code.
- Kích hoạt cơ chế giám sát có liên quan tới completion.
- Dọn một số tài nguyên thuộc quyền sở hữu stage, nếu callback luôn phải được chạy sau completion và cleanup được thiết kế an toàn.

Tuy nhiên, vì observer có thể thất bại, hãy quyết định có muốn lỗi quan sát tác động tới stage trả về không. Nếu logging là best effort, nên bắt lỗi có thể dự đoán trong observer và quản lý nó bằng kênh riêng. Nếu audit là yêu cầu bắt buộc để công nhận thành công, việc để lỗi audit làm stage mới thất bại **có thể** đúng, nhưng phải tránh đánh đồng lỗi audit với lỗi công việc nguồn khi trả API.

## 8. Hai lỗi cùng xảy ra: tránh đánh mất thông tin phụ

Hãy coi:
- **A** = lỗi từ công việc nguồn, chẳng hạn `IOException("database unavailable")`.
- **B** = lỗi từ observer, chẳng hạn `RuntimeException("metrics backend down")`.

Khi A và B đều xuất hiện, stage từ `whenComplete` ưu tiên A. Điều này đúng với mục đích **giữ nguyên lỗi của tác vụ chính**, nhưng không tạo ra bản báo cáo tự động về mọi lỗi bên lề.

### 8.1. Bẫy chỉ quan sát kết quả stage mới

~~~java
CompletableFuture<String> watched = source.whenComplete((value, error) -> {
    writeAuditRecord(value, error); // Có thể ném.
});
return watched;
~~~

Fragment giả định `source`, `writeAuditRecord` và một phương thức trả `CompletableFuture<String>`. Nếu `source` đã thất bại và `writeAuditRecord` cũng thất bại, caller của `watched` thường chỉ thấy nguyên nhân A. Sự cố B có thể không được báo qua kênh kết quả đó.

Nếu cần điều tra lỗi audit riêng, có thể dùng callback như:

~~~java
CompletableFuture<String> watched = source.whenComplete((value, error) -> {
    try {
        audit(value, error);
    } catch (RuntimeException auditFailure) {
        recordAuditFailure(auditFailure);
    }
});
~~~

Đây là fragment minh họa với các hàm chưa định nghĩa. Cách này bắt lỗi của `audit` một cách có chủ đích và gửi tới một kênh riêng. Nhưng bản thân `recordAuditFailure` cũng có thể thất bại. Hệ thống quan sát ở mức production cần một cơ chế có giới hạn, an toàn và có thể đối soát; không nên đẩy lỗi phụ vào một vòng lặp logging vô tận hoặc gọi một dịch vụ lỗi liên tục ở callback.

Nếu yêu cầu **phải lưu audit thành công trước khi xác nhận tác vụ**, hãy mô hình hóa audit thành một bước rõ ràng có kết quả độc lập và giao thức bền vững phù hợp. Không coi một callback `whenComplete` có in log là bảo đảm giao dịch dữ liệu + audit nguyên tử.

### 8.2. Có tự thêm suppressed exception không?

Đừng mặc định exception B của observer được Java tự động gắn vào A dưới dạng `getSuppressed()`. Quy tắc `whenComplete` xác định lỗi nào được ưu tiên làm kết cục stage; nó không cam kết cho caller một cấu trúc chứa đầy đủ cả hai exception. **Try-with-resources** có quy tắc riêng về suppressed exception khi body và `close()` cùng ném lỗi; không nên áp quy tắc ấy cho mọi callback `CompletionStage`.

Nếu ứng dụng cần giữ cả A lẫn B, hãy thiết kế `CombinedFailure` hoặc báo cáo lỗi riêng bằng dữ liệu có kiểu ở tầng điều phối, và kiểm chứng hành vi qua test. Khi hai lỗi độc lập xảy ra, có thể log B dưới nhãn lỗi observer và tiếp tục chuyển A với cause nguyên bản.

## 9. Lỗi observer khi nguồn thành công: ảnh hưởng tới API kết quả

Giả sử API hoàn thành một thao tác cập nhật thành công rồi gắn:

~~~java
CompletableFuture<Order> response = saveOrderAsync()
        .whenComplete((order, error) -> metricsClient.record(order, error));
~~~

Đây là fragment: `Order`, `saveOrderAsync()` và `metricsClient` là thành phần giả định. Nếu `saveOrderAsync()` thành công nhưng `metricsClient.record` ném exception, `response` có thể thất bại vì **observer**, dù đơn hàng đã được ghi.

Hệ quả thường gặp:
- Frontend nhận lỗi và retry thao tác tạo đơn.
- Retry có thể tạo đơn lần hai nếu thiếu idempotency.
- Monitoring báo tác vụ nghiệp vụ lỗi mặc dù ghi dữ liệu thành công.
- Người vận hành khó phân biệt “ghi đơn thất bại” với “ghi metric thất bại”.

Muốn giữ lỗi observer chỉ ở miền quan sát, cần chính sách xử lý riêng hoặc một luồng audit/metrics không được phép làm thay đổi kết quả nghiệp vụ. Nếu cần audit bắt buộc, cần phân biệt **thành công xử lý nghiệp vụ** và **thất bại công bố/audit**, kèm mã lỗi ổn định và trạng thái đối soát.

**Không nên bắt mọi `Throwable` trong logger chỉ để luôn giữ nghiệp vụ thành công**: `Error` hoặc vấn đề nghiêm trọng của JVM thường cần chiến lược riêng; nên xử lý những exception phù hợp theo phạm vi.

## 10. `whenComplete` chạy ở thread nào?

Tên `whenComplete` không có hậu tố Async. Với các dependent action không Async, hàm có thể được thực thi bởi **thread thực hiện việc hoàn thành stage**, hoặc thread khác tham gia lời gọi completion theo quy tắc của `CompletableFuture`. Nếu nguồn đã hoàn thành trước khi đăng ký, callback có thể được thực hiện ngay trong lời gọi tạo stage. Vì vậy:

- Không giả định callback luôn chạy trên “main thread”.
- Không giả định callback luôn chạy trên “worker thực hiện tác vụ nguồn”.
- Không dùng code yêu cầu UI thread/HTTP request context chỉ vì caller đã gọi `whenComplete` tại đó.
- Không thực hiện công việc chặn rất lâu trong callback mặc định nếu nó có thể làm chậm thread hoàn thành stage hoặc chuỗi phụ thuộc.

### 10.1. `whenCompleteAsync` và executor

Biến thể:

~~~java
CompletableFuture<String> observed =
        source.whenCompleteAsync((value, error) -> {
            recordMetrics(value, error);
        }, observerExecutor);
~~~

Fragment giả định `source`, `recordMetrics` và `observerExecutor` đã khai báo. Action được gửi thực thi bất đồng bộ qua executor do caller cung cấp. Điều này hữu ích để tách việc quan sát tốn thời gian khỏi thread hoàn thành tác vụ nguồn.

Nhưng các vấn đề vẫn còn:
- `whenCompleteAsync` **không biến action thành “không thể lỗi”**. Callback ném exception vẫn ảnh hưởng đến stage kết quả theo các quy tắc đã học.
- Executor có thể từ chối task (ví dụ đã shutdown), dẫn đến thất bại của stage phụ thuộc theo cơ chế executor.
- Nếu process kết thúc sớm, action bất đồng bộ có thể chưa chạy. Phải có cơ chế quản lý vòng đời nếu thực sự cần chờ observer hoàn tất.
- Nếu nguồn hoàn thành lỗi và callback cũng lỗi, quy tắc ưu tiên lỗi nguồn vẫn áp dụng cho lời gọi action khi nó được thực thi; nhưng vấn đề lên lịch thất bại của executor cần xử lý riêng.
- Tách sang executor khác không tự biến log/metrics thành bền vững hoặc đúng thứ tự với side effect nghiệp vụ.

Nếu bỏ qua `observed` sau khi gọi `whenCompleteAsync`, không có bảo đảm người gọi biết callback thất bại. Khi mục tiêu là ghi metric best effort, có thể có policy không lan lỗi; khi mục tiêu là audit bắt buộc, cần đảm bảo completion được theo dõi.

### 10.2. Không dựa vào thứ tự của nhiều observer ngang hàng

~~~java
source.whenComplete((value, error) -> logA(value, error));
source.whenComplete((value, error) -> logB(value, error));
~~~

Đây là fragment minh họa. Hai callback được gắn **độc lập** vào cùng nguồn; không nên giả định A chắc chắn hoàn tất trước B chỉ vì câu lệnh A nằm trước trong source code. Nếu cần thứ tự, tạo **chuỗi phụ thuộc**:

~~~java
CompletableFuture<T> chain = source
        .whenComplete((value, error) -> logA(value, error))
        .whenComplete((value, error) -> logB(value, error));
~~~

Đây là fragment cú pháp minh họa, cần khai báo kiểu `T`, `source` và các hàm. Ở mô hình chuỗi, callback thứ hai chạy sau khi stage thứ nhất hoàn thành. Tuy nhiên nếu A ném exception khi nguồn thành công, B sẽ nhận lỗi của stage trước; khi nguồn đã lỗi, các quy tắc ưu tiên tiếp tục áp dụng. Chính quan hệ phụ thuộc này cũng làm lỗi observer trở thành một phần luồng dữ liệu của chuỗi, nên cần cân nhắc mục tiêu.

## 11. Cancellation và timeout vẫn là exceptional completion cần quan sát

Với `CompletableFuture`:
- `cancel(...)` làm future hoàn thành ngoại lệ bằng `CancellationException` khi hủy thành công; không phải yêu cầu chắc chắn interrupt công việc nguồn.
- `orTimeout(...)` có thể làm future hoàn thành ngoại lệ với `TimeoutException` sau thời hạn nếu chưa hoàn thành.
- `completeOnTimeout(value, ...)` có thể hoàn thành future bình thường với giá trị dự phòng, nên `whenComplete` thấy **thành công của handle**, dù supplier vẫn có thể đang chạy.

Một observer:

~~~java
CompletableFuture<String> watched = source.whenComplete((value, error) -> {
    if (error == null) {
        recordSuccess();
    } else {
        recordFailure(error);
    }
});
~~~

Fragment giả định các hàm ghi nhận đã được khai báo. Khi source hủy hoặc timeout dẫn tới exceptional completion, observer nhận `error` phù hợp. Nhưng **completion của Future không chứng minh worker bên dưới đã dừng**. Đặc biệt, một supplier đang gọi HTTP có thể tiếp tục gây side effect sau khi `orTimeout` khiến future báo timeout.

Nếu `recordSuccess` chạy vì `completeOnTimeout("PENDING", ...)` đã hoàn thành future bình thường, metric “đã xử lý nghiệp vụ thành công” cũng có thể sai: cần phân biệt giá trị dự phòng `PENDING` với kết quả thực. Đừng dùng sự kiện `error == null` làm đồng nghĩa “remote đã commit”.

### 11.1. `get()`, `join()` và loại lỗi được thấy

Trên stage hoàn thành ngoại lệ:
- `join()` thông thường ném `CompletionException` chứa cause gốc; cancellation có thể ném `CancellationException` trực tiếp.
- `get()` ném `ExecutionException` chứa cause gốc khi tác vụ thất bại, có thể ném `InterruptedException` nếu thread chờ bị interrupt, và `CancellationException` nếu bị hủy.
- `get(timeout, unit)` còn có `TimeoutException` nếu caller chưa nhận kết quả trong thời hạn; đây là timeout của **việc chờ**, không tự biến source thành completed exceptionally như `orTimeout`.

Đừng nhầm một `TimeoutException` do `get(timeout)` trên caller với một `TimeoutException` đã được ghi thành trạng thái thất bại của source bởi `orTimeout`. Cùng tên exception nhưng vòng đời và mức độ tác động lên future khác nhau.

## 12. Observability đúng: log, metric và trace có chủ đích

Khi dùng `whenComplete` trong hệ thống thực tế, thông tin hữu ích gồm:

| Trường dữ liệu | Ví dụ | Mục đích |
| --- | --- | --- |
| `taskId` | `job-42` | Đối chiếu task cụ thể |
| `correlationId` | Request hoặc trace ID | Liên hệ các thành phần |
| `outcome` | `SUCCESS`, `FAILED`, `CANCELLED`, `TIMED_OUT` | Phân loại chính xác |
| `errorCode` | `STORAGE_UNAVAILABLE` | Nhóm lỗi ổn định |
| `causeType` | `IOException` | Chẩn đoán lỗi |
| `elapsedNanos` hoặc metric latency | Thời gian đã trôi qua | Điều tra hiệu năng |
| `observerOutcome` | `METRIC_OK` / `METRIC_FAILED` | Phân biệt sự cố quan sát với sự cố công việc |

Không nên đưa password, token, request payload riêng tư, dữ liệu khách hàng hoặc stack trace thô vào metric labels; nhiều hệ thống quan sát giới hạn cardinality, vì vậy không dùng `taskId` đơn nhất cho mọi metric label khi có thể tăng vô hạn. Log có thể chứa ID phù hợp, còn metric thường dùng nhãn tổng hợp ổn định.

Có thể đo khoảng thời gian bằng `System.nanoTime()` ở lúc bắt đầu task và tại callback kết thúc. Nhưng nếu callback được chạy trễ do executor tắc, thời gian ghi nhận có thể bao gồm độ trễ chờ observer; muốn đo chính xác “task đã hoàn thành ở mốc nào” thì cần instrument điểm hoàn thành thật sự hoặc truyền timestamp kết quả. Không đánh đồng latency của stage phụ với latency CPU của supplier.

### 12.1. Khi logging/metric code có thể thất bại

Nên trả lời rõ ba câu hỏi:
1. **Độ quan trọng:** quan sát lỗi có được phép làm API chính thất bại không?
2. **Ranh giới:** ai ghi nhận lỗi của bản thân observer?
3. **Khả năng phục hồi:** nếu metric sink chậm hoặc lỗi, có queue/buffer/circuit breaker/drop policy phù hợp không?

Nếu chỉ cần best effort, observer nên xử lý loại lỗi từ sink và không để nó phá nhánh nghiệp vụ. Nếu audit là điều kiện bắt buộc, nên xem nó như một bước nghiệp vụ/transactional protocol cần quản lý, có trạng thái riêng thay vì một side effect tùy hứng trong `whenComplete`.

Không tạo chuỗi callback tự gọi lại cùng future hoặc một vòng retry vô hạn trong observer khi downstream metric lỗi. Một observer chặn lâu có thể ảnh hưởng throughput nếu chạy trên thread hoàn thành; nếu tách async, cần giới hạn queue, số thread và lifecycle để không biến hệ thống quan sát thành nguồn quá tải.

## 13. Tương tác với `exceptionally`: thứ tự stage thay đổi ý nghĩa

Hai chuỗi sau không tương đương:

**Chuỗi A: quan sát lỗi gốc rồi mới phục hồi**

~~~java
CompletableFuture<String> recovered = source
        .whenComplete((value, error) -> audit(value, error))
        .exceptionally(error -> "fallback");
~~~

**Chuỗi B: phục hồi rồi mới quan sát**

~~~java
CompletableFuture<String> observed = source
        .exceptionally(error -> "fallback")
        .whenComplete((value, error) -> audit(value, error));
~~~

Đây là hai fragment giả định `source` là `CompletableFuture<String>` và `audit` có tham số tương thích; không phải hai file độc lập.

Ở A, `whenComplete` thấy **lỗi nguồn** trước khi có fallback. Nhưng nếu source thành công và audit ném lỗi, `exceptionally` phía sau có thể tạo fallback vì **lỗi audit**, gây thay đổi trạng thái API mà caller không mong muốn.

Ở B, `exceptionally` có thể chuyển lỗi nguồn thành giá trị `fallback` trước; `whenComplete` phía sau sẽ thấy một stage **thành công**, không còn trực tiếp thấy lỗi nguồn. Nếu audit lại ném, stage cuối vẫn có thể thất bại do observer.

Vì vậy hãy đặt quan sát ở đúng vị trí cần đo:
- **Quan sát lỗi thô:** trước recovery.
- **Quan sát kết quả cuối:** sau recovery.
- **Cần cả hai:** thiết kế hai điểm quan sát, mã phân loại riêng, và không dựa vào thứ tự callback độc lập.

Một `whenComplete` dùng để log mà ném exception có thể làm chính sách fallback nhận **lỗi logging**, không phải lỗi dịch vụ gốc. Test phải bao phủ điều đó.

## 14. Thao tác trong callback có side effect: không đồng nghĩa transactional

Việc callback nhận thông báo completion không nói rằng toàn bộ side effect bên ngoài đã được commit/rollback. Ví dụ:

~~~java
CompletableFuture<Order> stage = saveOrderAsync()
        .whenComplete((order, error) -> {
            if (error == null) {
                sendEmail(order);
            }
        });
~~~

Đây là fragment: các loại và hàm liên quan chưa định nghĩa. Nó có một rủi ro rõ ràng:
- `saveOrderAsync()` đã lưu đơn thành công.
- `sendEmail(order)` ném exception hoặc client timeout.
- Stage trả về `stage` có thể hoàn thành ngoại lệ vì observer, trong khi đơn hàng vẫn tồn tại.
- Caller retry tạo đơn nếu không có idempotency và quy tắc rõ ràng.

Nếu email/audit quan trọng, một cơ chế như **transactional outbox** có thể ghi bản ghi “cần gửi” cùng transaction DB; worker gửi sau commit và xử lý duplicate/idempotency. `whenComplete` không tự tạo transaction xuyên DB và hệ thống email.

Với cleanup, callback có thể đóng resource do nó sở hữu, nhưng cần chú ý:
- Đừng đóng resource dùng chung khi stage khác còn cần.
- Cleanup có thể ném exception và làm stage cuối thất bại.
- Nếu nguồn và cleanup cùng lỗi, lỗi nguồn được ưu tiên ở stage `whenComplete`; lỗi cleanup cần được ghi nhận nếu cần.
- Nếu cleanup thật sự phải chạy ngay cả khi process sắp tắt hoặc qua restart, chỉ dùng callback in-memory là chưa đủ.

## 15. Kiểm thử đầy đủ cả lỗi nguồn và lỗi observer

Đừng chỉ viết một test “observer được gọi khi success”. Một ma trận QA thích hợp:

| Tình huống | Dự đoán về `whenComplete` | Điều cần assert |
| --- | --- | --- |
| Nguồn success, observer success | Stage kết quả success | Giá trị đúng bằng source |
| Nguồn success với giá trị `null` | Observer nhận `(null, null)` | Không nhận nhầm failure |
| Nguồn failure, observer success | Stage kết quả failure nguồn | Cause/type đúng |
| Nguồn success, observer ném B | Stage kết quả failure B | Source vẫn success |
| Nguồn failure A, observer ném B | Stage kết quả failure A | Source A được ưu tiên |
| Observer best effort tự catch lỗi sink | Stage theo kết quả nguồn | Kênh phụ ghi nhận lỗi sink |
| `whenCompleteAsync` chạy trên executor cụ thể | Callback được lên lịch và chạy | Quan sát thread/lifecycle đúng, không có assumption sai |
| Observer executor từ chối task | Stage phụ thuộc có failure | Không lặng lẽ bỏ lỗi hạ tầng quan sát |
| Source bị hủy | Observer nhìn thấy exceptional completion | Không đánh đồng canceled với business failure |
| Source `orTimeout` | Observer thấy lỗi timeout của future | Không suy ra supplier đã dừng |
| `exceptionally` trước/sau observer | Callback thấy kết quả tại vị trí tương ứng | Lỗi không bị recovery che bất ngờ |
| Hai observer độc lập | Cả hai có thể được gọi | Không assert thứ tự nếu không đồng bộ |
| Ghi log/audit lỗi sau commit dữ liệu | Stage có thể failure observer | Dữ liệu đã commit không bị xem là rollback |

Để test ổn định, có thể dùng `CompletableFuture.completedFuture` và `completeExceptionally` tạo trạng thái nguồn một cách tất định, hoặc dùng `CountDownLatch` và executor kiểm soát khi cần xác minh race. Không dùng `Thread.sleep(100)` rồi cho rằng observer chắc chắn đã chạy. Dùng `observed.join()` hoặc cơ chế await có giới hạn khi bạn cần biết stage quan sát đã hoàn tất.

Ví dụ kiểm thử bằng JUnit 5 (fragment, giả định các import và class test đã có):

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("ok");
CompletableFuture<String> observed =
        source.whenComplete((value, error) -> {
            throw new IllegalStateException("observer failed");
        });

CompletionException ex = assertThrows(
        CompletionException.class, observed::join);

assertInstanceOf(IllegalStateException.class, ex.getCause());
assertEquals("ok", source.join());
~~~

Đây là **đoạn test minh họa không độc lập**, yêu cầu JUnit 5 và static imports `assertThrows`, `assertInstanceOf`, `assertEquals`. Điểm kiểm chứng là `observed` thất bại vì observer nhưng `source` vẫn thành công. Không cần tạo thread riêng để kiểm tra quy tắc ưu tiên exception.

### 15.1. Test khi cả A và B cùng ném

Tạo source bằng `completeExceptionally(A)`, sau đó gắn `whenComplete` action ném B. Dùng `observed.join()` và assert lỗi nguồn A còn là nguyên nhân của completion. Nếu cần lưu cả hai lỗi, test thêm logic ứng dụng **chủ động** ghi nhận B; không assert Java tự thêm B vào `getSuppressed()` khi hợp đồng không quy định.

## 16. Các lỗi phổ biến trong code thực tế

### Lỗi 1 — Dùng `value != null` để kết luận success

~~~java
future.whenComplete((value, error) -> {
    if (value != null) {
        recordSuccess();
    } else {
        recordFailure(error);
    }
});
~~~

Đây là fragment sai nếu future có thể thành công với `null`. Đúng hơn là kiểm tra `error == null`, rồi phân loại giá trị nghiệp vụ riêng.

### Lỗi 2 — Cho rằng `whenComplete` xử lý mất exception nguồn

~~~java
future.whenComplete((value, error) -> {
    if (error != null) {
        System.err.println(error);
    }
});
~~~

Fragment trên **quan sát** nhưng không phục hồi. Nếu nguồn lỗi, stage trả về vẫn lỗi. Muốn có giá trị thay thế, dùng `exceptionally` hoặc `handle` với hợp đồng rõ ràng.

### Lỗi 3 — Bỏ qua stage trả về

~~~java
future.whenComplete((value, error) -> publishAudit(value, error));
return future;
~~~

Fragment giả định `publishAudit` và chữ ký phương thức phù hợp. Caller nhận `future` nguồn, nên **không thể dựa vào nó** để biết audit đã hoàn thành hay lỗi. Nếu audit là thành phần bắt buộc, phải trả/đợi stage quan sát hoặc thiết kế kênh kết quả riêng, đồng thời giải quyết việc ưu tiên lỗi.

### Lỗi 4 — Observer lỗi nên retry nghiệp vụ đã thành công

Nếu ghi đơn thành công nhưng callback metrics thất bại, retry lưu đơn có thể nhân đôi side effect. Hãy phân biệt lỗi của nguồn và lỗi observer, dùng idempotency cho thao tác có tác động ngoài.

### Lỗi 5 — Tin rằng lỗi B luôn nằm trong `getSuppressed()` của A

Không có quy tắc chung như vậy cho `whenComplete`. Muốn biết cả A và B phải chủ động lưu/đếm/log B ở nơi an toàn.

### Lỗi 6 — Callback chặn lâu làm chậm pipeline

Vì `whenComplete` có thể chạy trên thread hoàn thành stage, một lời gọi HTTP từ observer có thể chiếm thread quan trọng. Có thể dùng `whenCompleteAsync` với executor riêng, nhưng phải quản lý queue, thời hạn, shutdown và thất bại lên lịch.

### Lỗi 7 — Dùng `whenCompleteAsync` mà không quản lý lifecycle

Một action chưa được scheduler chạy có thể bị bỏ qua khi ứng dụng kết thúc, hoặc trả về một stage failure nếu executor không còn nhận việc. Không biến `whenCompleteAsync` thành giải pháp audit bền vững chỉ vì tên chứa Async.

### Lỗi 8 — Chỉ log `error.getMessage()` mà bỏ cause

Nếu `error` là `CompletionException`, message có thể chỉ chứa loại wrapper; cần giữ cause có kiểu và ngữ cảnh task phù hợp. Không dùng message text làm mã lỗi ổn định, không leak dữ liệu nhạy cảm.

### Lỗi 9 — Dùng `whenComplete` thay `handle` cho phép chuyển kiểu

Callback `whenComplete` trả void, không cho phép `return new Failure(...)` để biến lỗi thành Result. Hãy chọn `handle` và trả một kết quả có kiểu cho mỗi nhánh.

### Lỗi 10 — Coi thứ tự callback độc lập là tất định

Khi nhiều observer đăng ký trên cùng nguồn, không dựa vào thứ tự nếu chúng không nối phụ thuộc. Với chuỗi nối stage, hãy nhớ callback trước ném lỗi sẽ ảnh hưởng đến callback sau.

## 17. Cây quyết định sử dụng `whenComplete`

~~~text
Muốn xử lý kết quả CompletableFuture?
|
+-- Muốn biến đổi giá trị success?  -> thenApply / thenCompose
|
+-- Muốn biến failure thành fallback? -> exceptionally
|
+-- Muốn biến cả success/failure
|   thành kết quả mới có kiểu? -> handle
|
+-- Chỉ muốn quan sát/cập nhật log/metric?
    |
    +-- Callback nhẹ, không block -> whenComplete
    |
    +-- Cần executor riêng -> whenCompleteAsync(action, executor)
    |
    +-- Quan sát bắt buộc bền vững?
        -> thiết kế audit/outbox/job state riêng,
           có cơ chế theo dõi lỗi và phục hồi
~~~

Sơ đồ định hướng thiết kế. Một API hoàn chỉnh có thể dùng **nhiều stage phối hợp**: xử lý công việc bằng `thenCompose`, quan sát failure nguyên bản bằng `whenComplete`, chuyển thành Result bằng `handle`, sau đó ghi metric cuối. Quan trọng là hiểu **thứ tự các phép nối và lỗi của chính callback**.

## 18. Checklist trước khi đưa vào production

1. **Kiểm tra đúng trạng thái:** `error == null` mới biểu thị completion bình thường; `value` có thể `null` ngay cả khi thành công.
2. **Không nhầm quan sát với recovery:** `whenComplete` không tự xử lý failure nguồn thành success.
3. **Hiểu quy tắc lỗi của callback:** source success + observer fail → stage trả về thất bại do observer; source fail + observer fail → lỗi source giữ ưu tiên.
4. **Phân biệt hai stage:** `source` và stage `observed` có thể mang hai trạng thái kết quả khác nhau.
5. **Quy định lỗi observer có ảnh hưởng nghiệp vụ không:** logging best effort khác audit bắt buộc.
6. **Đừng để mất lỗi B:** nếu lỗi quan sát cần giám sát, chủ động ghi nhận nó; không giả định hệ thống tự thêm suppressed exception.
7. **Biết thread nào chạy action:** `whenComplete` không cam kết thread cụ thể; `whenCompleteAsync` cần executor có lifecycle rõ.
8. **Không chặn thread completion quá lâu:** giới hạn I/O, metric và callback; cân nhắc executor riêng khi cần.
9. **Không đánh đồng Future timeout/cancel với worker đã dừng:** observer chỉ biết trạng thái completion của future đang theo dõi.
10. **Đặt observer theo đúng vị trí:** trước recovery để thấy lỗi gốc, sau recovery để thấy kết quả cuối; nhớ rằng observer ném cũng thay đổi kết cục stage sau nó.
11. **Quan sát stage trả về khi cần:** không bỏ qua lỗi của observer nếu đó là một phần hợp đồng.
12. **Kiểm thử cả bốn tổ hợp source/observer**, thêm null success, cancellation, timeout, async executor và side effect sau commit.

### Bài tập vận dụng

Một API `createInvoiceAsync()` trả `CompletableFuture<Invoice>`. Hệ thống muốn ghi metric và audit khi hoàn thành, đồng thời không được tạo hóa đơn trùng khi log thất bại.

1. Viết hai phiên bản pipeline: `whenComplete` cho metric best effort và một bước audit bắt buộc có trạng thái riêng.
2. Kiểm thử cả bốn tổ hợp: tạo hóa đơn thành công/thất bại; metric thành công/thất bại. Chỉ rõ lỗi nào đi tới caller của mỗi stage.
3. Thêm `exceptionally` làm fallback cho lỗi *được phép phục hồi*. Chứng minh vị trí `exceptionally` trước/sau `whenComplete` quyết định observer thấy lỗi nguồn hay kết quả fallback.
4. Nếu audit callback ném exception **sau khi hóa đơn đã được lưu**, xác định vì sao không thể coi hóa đơn đã rollback và đề xuất operation ID/idempotency cùng trạng thái đối soát.
5. Thử `whenCompleteAsync` với executor riêng và kiểm tra callback luôn được quan sát trước khi shutdown theo yêu cầu. Nếu logging có thể bị từ chối khi executor đã đóng, thiết kế kênh báo lỗi phù hợp.

**Điểm cần nhớ:** `whenComplete` là công cụ **quan sát hai nhánh thành công/thất bại** và tạo stage phụ thuộc. Nó không tự phục hồi exception. Một exception ném từ chính observer có thể làm stage mới thất bại; nếu nguồn đã thất bại, **lỗi nguồn được ưu tiên**. Thiết kế tốt phải giữ ranh giới rõ giữa công việc chính, việc quan sát, và chính sách xử lý lỗi của cả hai.