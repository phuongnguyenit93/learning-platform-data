# CompletableFuture với @Async trong phạm vi được hỗ trợ

Một truy vấn repository có thể mất thời gian chờ hệ thống lưu trữ. Nếu module hỗ trợ truy vấn bất đồng bộ, phương thức có thể trả về `CompletableFuture<T>` và dùng `@Async` để giao việc cho một executor của Spring.

Điều quan trọng là hiểu đúng kết quả: caller nhận được một future để theo dõi việc hoàn thành, còn công việc truy vấn được chạy ở nơi khác. Với truy vấn dùng JDBC/JPA, luồng worker vẫn có thể bị chặn trong lúc chờ database. Đây không phải sự chuyển đổi tự động sang truy cập dữ liệu reactive.

Trong phạm vi Spring Data Commons, `CompletableFuture` là một kiểu bao kết quả cần được đặt trong hợp đồng của module cụ thể. Không phải mọi repository, store, tổ hợp kiểu trả về hoặc phương thức đều hỗ trợ nó giống nhau.

Sau bài học, bạn cần có khả năng:

- Phân biệt kiểu bao kết quả, cơ chế `@Async` và khả năng thực thi của store.
- Cấu hình một executor có giới hạn cho truy vấn được hỗ trợ.
- Ghép các bước xử lý future mà không chặn không cần thiết.
- Xử lý lỗi, timeout và từ chối tác vụ đúng nghĩa.
- Xác định transaction, dữ liệu JPA và context nằm ở luồng nào.
- Chọn cách bao bất đồng bộ ở service khi module không hỗ trợ trực tiếp kiểu trả về repository.

## 1. Ba thành phần làm ba việc khác nhau

| Thành phần | Trách nhiệm | Không tự bảo đảm |
|---|---|---|
| `CompletableFuture<T>` | Đại diện cho kết quả sẽ hoàn thành, cho phép ghép các bước xử lý | Công việc đã chạy ở luồng khác |
| `@Async` và hạ tầng Spring | Chặn lời gọi qua proxy, gửi tác vụ tới executor | Store dùng I/O không chặn |
| Module Spring Data | Tạo truy vấn, bind, thực thi và ánh xạ kết quả | Mọi kiểu wrapper đều được hỗ trợ |

Chỉ đổi kiểu trả về từ `List<Customer>` sang `CompletableFuture<List<Customer>>` không đủ để tạo một truy vấn bất đồng bộ đúng hợp đồng.

Ngược lại, đặt `@Async` lên một phương thức bình thường nhưng gọi trực tiếp trên một đối tượng không đi qua proxy cũng không tự kích hoạt executor.

### 1.1. Điều kiện cần kiểm tra

Trước khi dùng trực tiếp trên repository, cần xác định:

1. Module và phiên bản có hỗ trợ asynchronous query methods không.
2. Kiểu trả về cụ thể có được hỗ trợ không.
3. Hạ tầng xử lý `@Async` đã được bật.
4. Lời gọi đi qua bean/proxy do Spring quản lý.
5. Executor phù hợp đã được chọn và cấu hình.
6. Chữ ký truy vấn, mapping và các điều kiện store vẫn hợp lệ.

Future không sửa được một tên phương thức suy diễn sai, một projection không ánh xạ được hoặc một truy vấn không được module triển khai.

## 2. Bất đồng bộ khác reactive

Với một repository JPA sử dụng truy vấn chặn, đường đi có thể hình dung như sau:

```text
Luồng caller:
  gọi repository proxy
      → gửi tác vụ
      → nhận CompletableFuture
      → tiếp tục làm việc khác

Luồng worker của executor:
  lấy tác vụ
      → gọi truy vấn JPA/JDBC
      → chờ database
      → ánh xạ kết quả
      → hoàn thành future
```

Caller được giải phóng khỏi việc chờ trực tiếp, nhưng hệ thống vẫn dùng một luồng cho công việc truy vấn đang chặn.

Một repository reactive dùng `Mono` hoặc `Flux` có hợp đồng thực thi, cách truyền tín hiệu và cơ chế điều tiết nhu cầu khác. Không thêm `@Async` vào reactive repository rồi coi đó là cách tiêu chuẩn để “bật reactive”.

| Đặc điểm | Async với truy vấn chặn | Repository reactive phù hợp |
|---|---|---|
| Kiểu kết quả tiêu biểu | `CompletableFuture<T>` | `Mono<T>`, `Flux<T>` |
| Cơ chế chính | Giao tác vụ sang executor | Chuỗi tín hiệu reactive và driver phù hợp |
| Luồng chờ truy vấn | Worker vẫn có thể bị chặn | Theo cơ chế không chặn của hạ tầng tương ứng |
| Điều tiết nhu cầu | Future không cung cấp backpressure theo phần tử | Có hợp đồng reactive liên quan |
| Dữ liệu nhiều phần tử | Một future có thể chứa cả danh sách | Có thể phát nhiều phần tử theo luồng |

`CompletableFuture<List<T>>` là một kết quả danh sách được hoàn thành như một giá trị. Nó không tự phát từng bản ghi theo nhu cầu người nhận.

## 3. Bật @Async và chọn executor có giới hạn

Ví dụ dưới đây minh họa cấu hình Spring cho một executor dành cho tác vụ truy vấn. Các con số chỉ để học cơ chế, không phải cấu hình tối ưu cho mọi ứng dụng.

```java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncQueryConfiguration {

    @Bean("repositoryQueryExecutor")
    public ThreadPoolTaskExecutor repositoryQueryExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("repository-query-");

        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy()
        );

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);

        return executor;
    }
}
```

Bean `ThreadPoolTaskExecutor` được Spring quản lý vòng đời; không cần tự gọi `initialize()` trong phương thức cấu hình này.

### 3.1. Ý nghĩa các giới hạn

- `corePoolSize`: số luồng lõi theo cơ chế của pool.
- `maxPoolSize`: mức tối đa pool có thể tăng tới.
- `queueCapacity`: số tác vụ chờ trong hàng đợi hữu hạn.
- `threadNamePrefix`: giúp nhận diện luồng khi quan sát.
- Chính sách từ chối: xác định điều gì xảy ra khi không nhận thêm tác vụ.
- Thiết lập shutdown: hỗ trợ quá trình dừng có thời gian chờ hữu hạn.

Với cơ chế `ThreadPoolExecutor`, tác vụ có thể được đưa vào queue sau khi các luồng lõi bận; pool không nhất thiết tăng ngay lên số luồng tối đa. Chỉ nhìn `maxPoolSize` chưa đủ để suy ra mức song song thực tế.

Thời gian chờ shutdown không phải query timeout. Hai cấu hình giải quyết hai vấn đề khác nhau.

### 3.2. Tại sao gọi tên executor?

```java
@Async("repositoryQueryExecutor")
```

Tên này thể hiện rõ nơi nhận tác vụ. Nếu ứng dụng có nhiều executor, không nên dựa vào suy đoán về executor mặc định.

Executor dành cho truy vấn chặn cũng cần được tính cùng connection pool và giới hạn database. Tăng số worker không làm database có thêm năng lực xử lý.

## 4. Ví dụ repository trong bối cảnh JPA hỗ trợ

Ví dụ sau đặt trong Spring Data JPA với asynchronous query methods được hỗ trợ. Giả sử entity `Customer` có các thuộc tính `id`, `tenantId`, `email`, `active`; kết nối, mapping và repository scanning đã được cấu hình.

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.scheduling.annotation.Async;

public interface AsyncCustomerRepository
        extends JpaRepository<Customer, Long> {

    @Async("repositoryQueryExecutor")
    CompletableFuture<List<Customer>> findByTenantIdAndActiveTrue(
        String tenantId
    );
}
```

Lời gọi từ một bean khác thông qua repository được inject:

```java
CompletableFuture<List<Customer>> pending =
    repository.findByTenantIdAndActiveTrue(tenantId);

// Caller có thể tiếp tục công việc độc lập tại đây.
```

Các điểm cần đọc đúng:

- `findByTenantIdAndActiveTrue` vẫn phải được suy diễn thành truy vấn hợp lệ.
- `tenantId` vẫn là điều kiện nghiệp vụ cần truyền đúng.
- `@Async` chọn executor.
- `CompletableFuture` bao kết quả và trạng thái hoàn thành.
- `List<Customer>` là dạng dữ liệu kết quả của truy vấn, không phải một luồng reactive.

Không sao chép nguyên chữ ký này sang một module khác chỉ vì module đó cũng kế thừa `Repository`.

### 4.1. Cardinality và giá trị rỗng vẫn cần hợp đồng

Với kiểu kết quả danh sách được hỗ trợ, không có phần tử phù hợp thường được biểu diễn bằng danh sách rỗng theo hợp đồng collection của repository.

Với một phương thức đơn kết quả, chẳng hạn `CompletableFuture<Customer>`, cần xem quy tắc không có kết quả, nhiều hơn một kết quả và nullability của repository. Future không tự thêm ý nghĩa `Optional`, cũng không tự biến lỗi nhiều kết quả thành một lựa chọn hợp lệ.

Các tổ hợp wrapper lồng nhau như `CompletableFuture<Optional<Customer>>` cần được xác nhận trên module và phiên bản cụ thể trước khi dùng. Không suy diễn rằng mọi kiểu bao đều có thể lồng tùy ý.

## 5. Ghép kết quả mà không chờ ngay tại caller

Future hữu ích khi caller có thể trả nó cho lớp hỗ trợ xử lý bất đồng bộ hoặc ghép các bước tiếp theo.

```java
CompletableFuture<List<Customer>> pending =
    repository.findByTenantIdAndActiveTrue(tenantId);

CompletableFuture<Integer> resultSize =
    pending.thenApply(List::size);
```

Ví dụ chỉ minh họa chuyển kiểu kết quả của future. Nếu nghiệp vụ chỉ cần đếm, nên dùng truy vấn đếm phù hợp thay vì tải toàn bộ entity rồi lấy kích thước danh sách.

### 5.1. Các toán tử thường dùng

| API | Khi chạy | Vai trò |
|---|---|---|
| `thenApply` | Khi bước trước thành công | Biến đổi giá trị `T` thành `U` |
| `thenCompose` | Khi bước trước thành công | Nối một bước vốn trả về future, tránh future lồng future |
| `thenCombine` | Khi hai kết quả cần thiết cùng thành công | Kết hợp hai giá trị |
| `whenComplete` | Khi thành công hoặc thất bại | Quan sát kết quả/lỗi |
| `exceptionally` | Khi thất bại | Chuyển lỗi thành giá trị dự phòng hoặc ném lỗi khác |
| `handle` | Khi thành công hoặc thất bại | Biến đổi cả hai trường hợp thành một kết quả mới |

Mỗi lời gọi tạo hoặc trả về một stage cần được sử dụng đúng. Không mặc định một lỗi trong callback sẽ được xử lý chỉ vì bạn giữ tham chiếu tới future gốc.

Ví dụ, nếu `thenApply` ném lỗi trong quá trình chuyển đổi, future kết quả của `thenApply` thất bại; future truy vấn trước đó có thể đã hoàn thành bình thường.

### 5.2. thenApply không cố định luồng chạy callback

Callback không có hậu tố `Async` có thể chạy trên luồng hoàn thành future, hoặc trên luồng đang đăng ký callback nếu kết quả đã có. Không viết logic dựa vào giả định nó luôn chạy trên luồng HTTP hoặc luôn trên một worker cụ thể.

Với biến thể `thenApplyAsync`, cần phân biệt:

- Không truyền executor: dùng executor mặc định của `CompletableFuture`, thường là `ForkJoinPool.commonPool()`.
- Truyền executor: dùng executor được chỉ định cho bước đó.

Bean executor của `@Async` không tự trở thành executor cho mọi callback có hậu tố `Async`.

Nếu cần định dạng một báo cáo tốn CPU sau khi đã lấy DTO, có thể chọn executor phù hợp cho bước định dạng. Không để một callback truy cập association lazy với kỳ vọng nó còn ở trong transaction truy vấn.

### 5.3. Chờ nhóm future không tạo giới hạn đồng thời

Giả sử `first` và `second` là hai `CompletableFuture<List<CustomerSummary>>` đã được tạo cho hai công việc độc lập:

```java
CompletableFuture<Integer> totalSize =
    CompletableFuture.allOf(first, second)
        .thenApply(ignored ->
            first.join().size() + second.join().size()
        );
```

Trong callback này, `join()` chỉ đọc các kết quả đã hoàn thành bình thường, vì `thenApply` chạy sau khi `allOf` thành công.

Tuy nhiên:

- `allOf` không tự thu thập giá trị thành danh sách.
- Một future con lỗi có thể làm future nhóm hoàn thành lỗi.
- Nó không tự hủy những truy vấn khác khi một truy vấn lỗi.
- Nó không tự giới hạn số tác vụ đã được gửi.
- Việc hai truy vấn chạy song song không tạo một transaction hay snapshot chung.

Gửi hàng nghìn truy vấn rồi gọi `allOf` không phải cơ chế điều tiết tải.

## 6. get và join: điểm caller bắt đầu chờ

```java
List<Customer> rows = pending.join();
```

Lời gọi này chặn luồng hiện tại cho tới khi future hoàn thành. Nếu thực hiện ngay sau khi gọi repository, caller lại phải chờ trong lúc một worker khác đang làm truy vấn.

| Lời gọi | Hành vi chờ | Lỗi đáng chú ý |
|---|---|---|
| `get()` | Chờ kết quả | `InterruptedException`, `ExecutionException` |
| `get(timeout, unit)` | Chờ có giới hạn | Thêm `TimeoutException` |
| `join()` | Chờ kết quả | Thường bọc lỗi bằng `CompletionException` |
| Future bị cancel | Không có kết quả bình thường | Có thể nhận `CancellationException` |

`join()` không phải một phiên bản không chặn của `get()`. Khác biệt quan trọng là cách biểu diễn exception và hợp đồng API.

Nếu một luồng bắt `InterruptedException` mà không tiếp tục ném nó, cần xử lý chính sách interruption phù hợp, thường bao gồm khôi phục cờ interrupt. Đừng biến mọi lỗi chờ thành danh sách rỗng.

Việc chờ có thể hợp lý tại ranh giới buộc phải đồng bộ. Nhưng cần làm rõ lợi ích của việc giao truy vấn sang executor nếu cuối cùng caller vẫn đứng chờ ngay lập tức.

## 7. Lỗi có thể xuất hiện trước và sau khi nhận future

### 7.1. Lỗi trước khi tác vụ được nhận

Executor có giới hạn có thể từ chối tác vụ. Với cấu hình từ chối bằng exception, lời gọi qua proxy có thể ném lỗi ngay ở bước gửi việc, chẳng hạn `TaskRejectedException`.

Khi đó, không thể mặc định đã có một future để gắn `exceptionally`.

Tương tự, một lỗi cấu hình hoặc lỗi tạo query có thể được phát hiện khi khởi tạo repository hoặc trước khi công việc tới worker.

### 7.2. Lỗi trong công việc bất đồng bộ

Nếu công việc đã chạy và truy vấn thất bại, future có thể hoàn thành exceptionally. Lỗi dữ liệu, lỗi kết nối, timeout ở tầng driver hoặc lỗi ánh xạ kết quả đều có thể đi theo đường này.

Khi đọc qua `get()` hoặc `join()`, cần xem nguyên nhân bên trong wrapper thay vì chỉ ghi nhận tên `ExecutionException` hoặc `CompletionException`.

### 7.3. Quan sát khác với phục hồi

Có thể dùng `whenComplete` để ghi nhận kết quả và lỗi. Callback quan sát cũng cần được viết cẩn thận: nếu nó ném exception, stage trả về có thể bị ảnh hưởng.

`exceptionally` và `handle` có khả năng chuyển thất bại thành thành công với một giá trị khác. Điều đó phải phù hợp nghiệp vụ.

Ví dụ cần tránh nếu không có chủ đích:

```java
CompletableFuture<List<Customer>> recovered =
    pending.exceptionally(error -> List.of());
```

Đoạn này có thể khiến “database đang lỗi” trở thành “không có khách hàng phù hợp”. Hai tình huống không có cùng ý nghĩa.

Một giá trị dự phòng từ cache có thể hợp lệ nếu API đã định nghĩa rõ, nhưng cần phân biệt dữ liệu dự phòng với kết quả truy vấn bình thường.

Với phương thức `@Async` trả future, lỗi công việc cần được theo dõi qua future. Không kỳ vọng cơ chế xử lý exception cho phương thức `void @Async` sẽ thay thế việc quan sát future.

## 8. Timeout không đồng nghĩa hủy truy vấn database

Ba thao tác dễ bị nhầm:

| API | Điều thay đổi | Điều không được suy ra |
|---|---|---|
| `get(2, SECONDS)` | Luồng đang chờ dừng chờ khi hết hạn | Future đã thất bại hoặc truy vấn đã dừng |
| `orTimeout(2, SECONDS)` | Future được hoàn thành lỗi nếu chưa xong khi hết hạn | JDBC statement đã bị hủy |
| `completeOnTimeout(fallback, 2, SECONDS)` | Future được hoàn thành bình thường bằng giá trị dự phòng khi hết hạn | Công việc nguồn đã dừng hoặc thực sự không có dữ liệu |

Ví dụ, trên phiên bản Java hỗ trợ API này:

```java
import java.util.concurrent.TimeUnit;

CompletableFuture<List<Customer>> pending =
    repository.findByTenantIdAndActiveTrue(tenantId);

pending.orTimeout(2, TimeUnit.SECONDS);
```

`orTimeout` tác động lên chính future đó và trả về nó; đây không chỉ là một thao tác chờ có thời hạn của một caller. Khi hết hạn, việc query ở tầng dưới có thể vẫn tiếp tục chiếm worker và connection.

Thời gian nằm trong queue cũng có thể tiêu thụ thời hạn mà caller đang theo dõi. Cần phân biệt:

- Thời gian chờ tác vụ bắt đầu.
- Thời gian lấy connection.
- Thời gian thực thi query.
- Thời gian ánh xạ và xử lý tiếp.
- Thời hạn tổng của lời gọi nghiệp vụ.

Muốn giới hạn công việc ở tầng dữ liệu phải xem query timeout, transaction timeout, timeout của driver hoặc cơ chế hủy mà hạ tầng cụ thể hỗ trợ.

### 8.1. cancel(true) không phải bằng chứng đã dừng SQL

```java
pending.cancel(true);
```

Đối với `CompletableFuture`, không được coi đối số `true` là cam kết sẽ interrupt được worker rồi hủy query đang chạy. Trạng thái canceled của future và trạng thái tác vụ truy vấn là hai điều phải kiểm tra riêng.

Nếu retry ngay sau timeout mà truy vấn cũ vẫn chạy, tải thực tế có thể tăng thêm. Với thao tác ghi, còn phải quan tâm kết quả chưa xác định và tính idempotent; timeout ở caller không chứng minh transaction đã rollback.

## 9. Transaction không tự đi theo future sang luồng khác

Trong mô hình transaction đồng bộ thông thường của Spring, tài nguyên transaction gắn với luồng thực thi. Một caller đang có `@Transactional` không tự truyền transaction đó sang worker của `@Async`.

```text
Luồng caller:
  transaction A đang hoạt động
      → gọi async repository
      → tiếp tục hoặc kết thúc transaction A

Luồng worker:
  thực thi query theo ranh giới transaction của chính công việc đó
```

Không được hiểu future là một “tay cầm” kéo dài transaction của caller cho tới khi có kết quả.

### 9.1. Vòng đời entity JPA cũng không được kéo dài

Một future đã hoàn thành chứa entity không có nghĩa persistence context vẫn mở. Sau khi ranh giới truy vấn/transaction kết thúc, việc callback truy cập association lazy có thể thất bại hoặc phát sinh hành vi ngoài dự kiến.

Ngay cả khi callback tình cờ chạy trên cùng worker vừa truy vấn, transaction có thể đã kết thúc trước callback.

Nếu kết quả cần đi qua ranh giới luồng hoặc ranh giới ứng dụng, nên thiết kế DTO/projection phù hợp. Khi cần đọc association, hãy lấy dữ liệu và chuyển đổi trong ranh giới đọc đã xác định.

### 9.2. Hai truy vấn async không tạo transaction chung

Chạy song song hai truy vấn rồi dùng `thenCombine` không cung cấp:

- Cùng một persistence context.
- Cùng một JDBC connection.
- Cùng snapshot dữ liệu.
- Tính nguyên tử khi một thao tác thành công còn thao tác kia thất bại.

Nếu nghiệp vụ cần tính nhất quán như một đơn vị, phải thiết kế ranh giới transaction theo yêu cầu, thay vì chỉ kết hợp future.

## 10. Bao bất đồng bộ ở service với ranh giới rõ ràng

Khi module không hỗ trợ trực tiếp một chữ ký repository trả `CompletableFuture`, hoặc cần kiểm soát transaction và chuyển đổi DTO, có thể giữ repository đồng bộ rồi giao cả công việc service sang executor.

Đây là một thiết kế ở tầng ứng dụng, không phải cách bổ sung khả năng asynchronous query methods cho module.

Ví dụ sau vẫn đặt trong bối cảnh JPA. Các kiểu được trình bày thành những đoạn độc lập; dự án thực tế cần package, entity và cấu hình tương ứng. Phần dùng `record` và `Stream.toList()` giả định Java 17 trở lên.

### 10.1. Repository đồng bộ

```java
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerReadRepository
        extends JpaRepository<Customer, Long> {

    List<Customer> findByTenantIdAndActiveTrue(String tenantId);
}
```

### 10.2. DTO chứa dữ liệu cần trả

```java
public record CustomerSummary(Long id, String email) {
}
```

### 10.3. Bean đọc dữ liệu trong transaction

```java
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerReadService {

    private final CustomerReadRepository repository;

    public CustomerReadService(CustomerReadRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<CustomerSummary> loadActive(String tenantId) {
        return repository.findByTenantIdAndActiveTrue(tenantId)
            .stream()
            .map(customer -> new CustomerSummary(
                customer.getId(),
                customer.getEmail()
            ))
            .toList();
    }
}
```

### 10.4. Bean giao công việc sang executor

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncCustomerFacade {

    private final CustomerReadService readService;

    public AsyncCustomerFacade(CustomerReadService readService) {
        this.readService = readService;
    }

    @Async("repositoryQueryExecutor")
    public CompletableFuture<List<CustomerSummary>> loadActive(
        String tenantId
    ) {
        List<CustomerSummary> summaries =
            readService.loadActive(tenantId);

        return CompletableFuture.completedFuture(summaries);
    }
}
```

Caller ở bean khác gọi bean `AsyncCustomerFacade` được inject:

```java
CompletableFuture<List<CustomerSummary>> result =
    asyncCustomerFacade.loadActive(tenantId);
```

Đường đi:

```text
Caller
  → proxy AsyncCustomerFacade gửi tác vụ
      → worker chạy loadActive
          → proxy CustomerReadService bắt đầu transaction đọc
              → repository đồng bộ truy vấn
              → tạo DTO
          → transaction kết thúc
      → hoàn thành future với DTO
```

Hai bean làm rõ hai ranh giới: chuyển luồng và transaction. DTO được tạo trước khi rời phần đọc dữ liệu.

`CompletableFuture.completedFuture(...)` không tự tạo luồng. Trong ví dụ, `@Async` qua proxy mới là phần giao công việc sang executor; phương thức bên trong trả một future đã có giá trị để hạ tầng async hoàn tất hợp đồng.

Không dùng thêm một repository `@Async` bên trong facade này rồi `join()` kết quả. Thiết kế ở đây chủ đích gọi repository đồng bộ từ worker.

## 11. Proxy và context: lời gọi phải đi đúng đường

### 11.1. Self-invocation không kích hoạt proxy @Async mặc định

Nếu trong cùng đối tượng có:

```java
this.loadActive(tenantId);
```

lời gọi trực tiếp không đi qua async proxy trong mô hình proxy mặc định. Annotation trên phương thức không đủ để chuyển công việc sang worker trong trường hợp đó.

Tương tự, tự tạo đối tượng bằng `new` rồi gọi phương thức không sử dụng hạ tầng proxy của bean được Spring quản lý.

Thiết kế facade được gọi từ bean khác giúp thể hiện rõ lời gọi đi qua proxy. Ranh giới transaction cũng cần lời gọi qua hạ tầng tương ứng; không chỉ thêm annotation rồi bỏ qua cách bean được gọi.

### 11.2. ThreadLocal không tự trở thành context của mọi tác vụ

Các dữ liệu sau cần được xem xét khi chuyển luồng:

- Tenant hoặc thông tin phạm vi truy cập.
- Security context.
- Mã correlation và logging MDC.
- Locale hoặc những giá trị request-specific.
- Những tài nguyên transaction gắn với luồng.

Không mặc định mọi `ThreadLocal` của caller xuất hiện trong executor. Có thể truyền dữ liệu cần thiết bằng tham số hoặc dùng cơ chế propagation phù hợp, chẳng hạn task decorator cho context thích hợp.

Không truyền `EntityManager`, connection đang dùng hoặc entity đang được chỉnh sửa đồng thời sang nhiều tác vụ như thể chúng là dữ liệu thread-safe. Truyền định danh hoặc dữ liệu đầu vào độc lập thường dễ kiểm soát hơn.

Khi truyền `tenantId`, nguồn giá trị phải đúng với ngữ cảnh quyền của lời gọi. Chuyển sang worker không được làm mất điều kiện giới hạn dữ liệu.

## 12. Giới hạn tải và tránh tự chặn executor

### 12.1. Worker, queue và connection pool phải được xem cùng nhau

Nếu nhiều worker cùng chờ connection, số luồng lớn hơn không làm truy vấn nhanh hơn. Nó có thể làm tăng lượng tác vụ treo, bộ nhớ và độ trễ.

Queue cũng không tạo thêm năng lực xử lý. Một queue rất dài có thể khiến caller hết thời hạn trước khi công việc bắt đầu, trong khi công việc cũ vẫn tiếp tục tiêu thụ tài nguyên.

Khi thiết kế cần xem:

- Số query đang chạy và thời gian chờ connection.
- Số worker bận, độ dài queue và số tác vụ bị từ chối.
- Độ trễ thực thi query và độ trễ tổng.
- Số tác vụ được tạo từ một request hoặc một job.
- Giới hạn của database và tải từ các luồng khác.

Không có backpressure theo phần tử từ `CompletableFuture`. Ứng dụng phải tự quyết định giới hạn đồng thời và cách phản hồi khi quá tải.

### 12.2. Chờ tác vụ con trong cùng pool có thể gây kẹt

Giả sử một pool có bốn worker. Cả bốn đang chạy những tác vụ ngoài. Mỗi tác vụ lại gửi một truy vấn async vào chính pool đó rồi gọi `join()`.

```text
4 worker:
  đều chờ future con

Queue:
  chứa các truy vấn con đang đợi worker

Kết quả:
  không còn worker để chạy công việc mà các worker đang chờ
```

Đây là vấn đề phân bổ công việc, không phải lỗi cú pháp truy vấn. Tăng thời gian chờ không giải quyết nguyên nhân.

Có thể tránh bằng cách chỉ có một ranh giới async cho công việc chặn, như facade gọi repository đồng bộ, hoặc ghép future mà không giữ worker đứng chờ tác vụ con.

### 12.3. commonPool không tự hiểu giới hạn truy vấn của ứng dụng

Dùng `CompletableFuture.supplyAsync(...)` không truyền executor sẽ chọn cơ chế executor mặc định của Java. Nó không tự dùng bean `repositoryQueryExecutor` đã cấu hình và không tự truyền transaction của caller.

Nếu chủ động chọn cách này, cần tự thiết kế executor, context, transaction và cách theo dõi lỗi. Không dùng nó như một thao tác thay thế tương đương với lời gọi qua `@Async` của Spring.

## 13. Chọn ranh giới bất đồng bộ theo yêu cầu

| Tình huống | Lựa chọn cần xem xét |
|---|---|
| Module hỗ trợ async query methods và chữ ký phù hợp | Dùng `@Async` cùng kiểu future được module hỗ trợ |
| Chỉ có repository đồng bộ hoặc cần kiểm soát transaction/DTO | Bao công việc ở service async, gọi phần đọc đồng bộ có ranh giới rõ |
| Hạ tầng truy cập dữ liệu đã reactive | Giữ hợp đồng reactive thích hợp, tránh bọc thêm async một cách tùy ý |
| Caller phải chờ ngay và không có công việc độc lập | Cân nhắc truy vấn đồng bộ với hợp đồng đơn giản |
| Nhiều truy vấn cần một transaction nhất quán | Thiết kế một đơn vị transaction trước khi quyết định chạy song song |
| Query đang quá chậm hoặc trả quá nhiều dữ liệu | Tối ưu query, projection, index và giới hạn dữ liệu cùng với thiết kế executor |

Asynchronous query methods là khả năng cần đối chiếu theo module và phiên bản. Kiểu `CompletableFuture` xuất hiện trong tài liệu chung không đủ chứng minh một module hỗ trợ mọi phương thức CRUD, query, projection hoặc wrapper lồng nhau.

Future cũng là trạng thái trong tiến trình ứng dụng, không phải bản ghi công việc bền vững. Nếu yêu cầu là một job phải tiếp tục sau khi tiến trình khởi động lại, cần một thiết kế quản lý công việc riêng.

## 14. Chẩn đoán và kiểm chứng trong dự án thực tế

### 14.1. Quan sát đúng vị trí thực thi

Khi kiểm chứng, cần biết:

- Luồng gọi proxy.
- Luồng chạy phần thân công việc/query.
- Executor đã nhận tác vụ.
- Vị trí bắt đầu và kết thúc transaction.
- Vị trí callback xử lý kết quả.

Một callback chạy trên luồng caller không chứng minh `@Async` bị hỏng: nếu future đã hoàn thành trước khi callback được đăng ký, callback không có hậu tố `Async` có thể chạy ngay ở luồng đăng ký.

Tương tự, không viết kiểm tra luôn yêu cầu `future.isDone()` phải bằng `false` ngay sau lời gọi. Một công việc rất nhanh có thể hoàn thành trước khi caller kiểm tra trạng thái.

### 14.2. Phân biệt các lỗi qua triệu chứng

| Triệu chứng | Điều cần kiểm tra |
|---|---|
| Công việc chạy trực tiếp trên caller | `@EnableAsync`, bean được quản lý, self-invocation và proxy |
| Query không được tạo | Module, chữ ký future, tên truy vấn và mapping |
| Không nhận được future do exception ngay tại lời gọi | Executor từ chối hoặc lỗi trước khi gửi công việc |
| Future hoàn thành lỗi | Nguyên nhân query, kết nối, chuyển đổi hoặc callback |
| Sau timeout database vẫn bận | Timeout của future khác timeout/hủy ở tầng dữ liệu |
| Lazy loading lỗi trong callback | Transaction/persistence context đã kết thúc |
| Nhiều worker đứng chờ nhưng không có tiến triển | Tác vụ con trong cùng pool và chờ bằng `join/get` |
| Context tenant hoặc logging bị mất | Cách truyền tham số và propagation context |
| Chạy được nhưng tải cao làm độ trễ tăng mạnh | Queue, worker, connection pool và giới hạn đồng thời |

### 14.3. Kiểm chứng hợp đồng thay vì chỉ kiểm tra tên kiểu

Một bộ tình huống có ích trong dự án thực tế:

1. Query thành công và query không có dữ liệu.
2. Query thất bại, bảo đảm lỗi không bị biến thành kết quả rỗng.
3. Executor quá tải, quan sát cách lời gọi bị từ chối.
4. Caller hết thời hạn, xác định trạng thái future và công việc nguồn.
5. DTO được tạo trong ranh giới đọc, không phụ thuộc lazy loading ở callback.
6. Nhiều lời gọi độc lập, kiểm tra giới hạn tài nguyên và dữ liệu đúng phạm vi.
7. Đóng ứng dụng khi còn công việc, xác định chính sách chờ và xử lý công việc chưa xong.

Một mock repository trả sẵn `CompletableFuture.completedFuture(...)` hữu ích cho logic ghép kết quả, nhưng không chứng minh proxy `@Async`, transaction và query creator của store hoạt động đúng.

## 15. Bài tập vận dụng

### Bài tập 1: Kiểu trả về có tạo luồng không?

Một phương thức trả:

```java
return CompletableFuture.completedFuture(loadSynchronously());
```

Không có `@Async`, không có executor được sử dụng trong lời gọi. `loadSynchronously()` có tự chạy ở luồng khác không?

**Gợi ý lời giải:** Không. Java phải tính đối số `loadSynchronously()` trước khi tạo future đã hoàn thành. Muốn chuyển công việc cần một cơ chế thực thi bất đồng bộ thật sự; trong ví dụ service của bài, đó là lời gọi qua proxy `@Async`.

### Bài tập 2: Gọi join ngay sau truy vấn

Caller gọi repository async rồi lập tức `join()`. Điều gì xảy ra?

**Gợi ý lời giải:** Caller chờ trong khi worker thực hiện query. Kiểu trả về vẫn là future, nhưng caller chưa tận dụng được khả năng tiếp tục làm việc hoặc trả kết quả bất đồng bộ cho tầng hỗ trợ. Việc thêm worker không tự làm query nhanh hơn.

### Bài tập 3: Transaction của caller

Một service có `@Transactional` thay đổi dữ liệu rồi gọi một repository async trước khi transaction caller commit. Worker có chắc chắn đọc thấy các thay đổi chưa commit không?

**Gợi ý lời giải:** Không. Transaction đồng bộ gắn với luồng caller không tự truyền sang worker. Khả năng nhìn thấy dữ liệu còn phụ thuộc commit, isolation và ranh giới query riêng; future không cung cấp bảo đảm đọc chung transaction.

### Bài tập 4: Timeout hai giây

Caller đặt `orTimeout(2, SECONDS)`. Sau hai giây future báo timeout, nhưng database tiếp tục chạy query trong vài giây nữa. Đây có phải mâu thuẫn không?

**Gợi ý lời giải:** Không. Future đã được hoàn thành lỗi theo thời hạn, còn việc hủy công việc dữ liệu là một cơ chế khác. Cần cấu hình và kiểm chứng timeout ở tầng query/driver phù hợp; không suy từ trạng thái future rằng tài nguyên đã được giải phóng.

### Bài tập 5: Bốn worker chờ bốn tác vụ con

Một pool cố định bốn worker có bốn tác vụ đang chạy. Mỗi tác vụ gửi một query con vào cùng pool rồi `join()`. Vì sao hệ thống có thể đứng lại?

**Gợi ý lời giải:** Các worker đều đang chờ; query con trong queue không có worker để chạy. Cần bỏ việc chờ lồng nhau hoặc chỉ giữ một ranh giới async cho công việc chặn.

### Bài tập 6: Module chưa hỗ trợ future trên repository

Một module chỉ cung cấp phương thức query đồng bộ phù hợp. Có thể tuyên bố module hỗ trợ asynchronous query methods bằng cách bao nó trong một service `@Async` không?

**Gợi ý lời giải:** Không. Đây là bất đồng bộ ở tầng ứng dụng. Nó có thể là thiết kế phù hợp, nhưng repository vẫn thực thi theo hợp đồng đồng bộ; service chịu trách nhiệm executor, transaction, context và future.

## 16. Những điều cần ghi nhớ

- `CompletableFuture` bao trạng thái/kết quả; nó không tự tạo công việc bất đồng bộ.
- `@Async` cần hạ tầng được bật và lời gọi đi qua proxy phù hợp.
- Chữ ký repository async phải được module và phiên bản thực tế hỗ trợ.
- Giao truy vấn JPA/JDBC sang worker vẫn có thể là I/O chặn, với giới hạn worker và connection.
- `join/get` chặn caller; callback và executor cần được thiết kế có chủ đích.
- Timeout/cancel ở future không chứng minh query đã bị hủy hoặc transaction đã rollback.
- Transaction và context của caller không tự đi sang worker.
- Khi cần kiểm soát ranh giới, có thể dùng service async gọi phần đọc đồng bộ có transaction rồi trả DTO.
