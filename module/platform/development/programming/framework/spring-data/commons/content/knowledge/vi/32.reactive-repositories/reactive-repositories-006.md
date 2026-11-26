# Tham số Publisher và kiểu kết quả rỗng

## Mục tiêu và phạm vi

Trong repository reactive của Spring Data, `Publisher` không chỉ xuất hiện ở kiểu trả về. Một số phương thức còn nhận publisher làm tham số để lấy ID hoặc entity khi pipeline được thực thi.

Ví dụ:

```java
Mono<Product> product = repository.findById(idPublisher);
```

Lời gọi này đặt ra hai câu hỏi độc lập:

1. Repository lấy bao nhiêu giá trị từ publisher đầu vào?
2. Publisher kết quả biểu diễn điều gì khi không có dữ liệu?

Không thể trả lời chỉ bằng cách thấy từ `Publisher` hoặc `Mono`. Cần đọc hợp đồng của từng phương thức và phân biệt **đầu vào không phát phần tử**, **truy vấn không tìm thấy**, **giá trị false**, **completion không có giá trị** và **lỗi**.

Bài học tập trung vào các overload của `ReactiveCrudRepository` trong Spring Data Commons. Ví dụ mapping sử dụng R2DBC; derived query và các khả năng nâng cao vẫn phụ thuộc module store.

## 1. Có hai publisher trong một lời gọi

Một phương thức nhận publisher và trả publisher có hai phía:

```text
Publisher<ID> đầu vào
    -> cung cấp ID theo hợp đồng method
    -> repository thực hiện thao tác với store
    -> Publisher kết quả phát dữ liệu, hoàn tất hoặc lỗi
```

Ví dụ:

```java
Publisher<Long> idSource = Mono.just(10L);

Mono<Product> result = repository.findById(idSource);
```

`idSource` cung cấp ID. `result` cung cấp sản phẩm hoặc tín hiệu kết thúc của thao tác. Chúng không phải cùng một chuỗi dữ liệu và không có cùng cardinality chỉ vì đều là publisher.

Ứng dụng thường trả `result` cho bên gọi hoặc framework. Không cần tự subscribe `idSource` để lấy ID trước, cũng không cần `block()` rồi truyền ID đã lấy vào repository.

Với đường truy cập dữ liệu được trì hoãn theo subscription, pipeline khái quát là:

```text
Bên sử dụng subscribe kết quả
    -> repository đăng ký với nguồn tham số
    -> nhận tham số cần thiết
    -> thực hiện truy cập store
    -> đưa kết quả về bên sử dụng
```

Chi tiết subscription, buffering và thực thi thuộc implementation. Kiểu tham số `Publisher` không tự bảo đảm mỗi phần tử đầu vào tương ứng một câu query riêng.

## 2. Publisher là một giao thức, không phải một collection có sẵn

Trong bài này, `Publisher` là:

```java
import org.reactivestreams.Publisher;
```

Một publisher có thể:

- Phát không có phần tử rồi hoàn tất.
- Phát một phần tử.
- Phát nhiều phần tử.
- Phát lỗi.
- Không hoàn tất.
- Có hành vi khác nhau khi được subscribe lại.

Vì vậy, một `Publisher<Long>` không mặc định là một ID duy nhất, cũng không mặc định là một danh sách ID hữu hạn đã sẵn sàng trong bộ nhớ.

Những trạng thái sau khác nhau:

```java
Publisher<Long> oneId = Mono.just(10L);
Publisher<Long> noId = Mono.empty();
Publisher<Long> severalIds = Flux.just(10L, 20L, 30L);
Publisher<Long> failedId = Mono.error(
        new IllegalStateException("Cannot resolve the identifier")
);
```

Publisher đầu vào phải là một đối tượng hợp lệ. Không dùng `null` thay cho một publisher rỗng.

Reactor cũng không phát phần tử `null`:

```java
Long nullableId = null;

Mono<Long> idSource = Mono.justOrEmpty(nullableId);
```

`idSource` ở đây hoàn tất rỗng. Nó khác với `Mono.just(null)`, vốn không phải cách tạo một phần tử hợp lệ.

## 3. Mỗi overload có quy tắc tiêu thụ riêng

Những dạng quan trọng của `ReactiveCrudRepository<T, ID>` gồm:

| Phương thức | Tham số publisher | Cách hiểu đầu vào | Kết quả |
|---|---|---|---|
| `findById(Publisher<ID>)` | Nguồn ID | Dùng ID được phát đầu tiên | `Mono<T>` |
| `existsById(Publisher<ID>)` | Nguồn ID | Dùng ID được phát đầu tiên | `Mono<Boolean>` |
| `deleteById(Publisher<ID>)` | Nguồn ID | Dùng ID được phát đầu tiên | `Mono<Void>` |
| `findAllById(Publisher<ID>)` | Nguồn các ID | Tìm các entity ứng với những ID được cung cấp | `Flux<T>` |
| `saveAll(Publisher<S>)` | Nguồn entity | Lưu các entity từ nguồn theo hợp đồng | `Flux<S>` |
| `deleteAll(Publisher<? extends T>)` | Nguồn entity | Xóa các entity từ nguồn theo hợp đồng | `Mono<Void>` |

Ba phương thức có tên `...ById` ở ba hàng đầu không có nghĩa là “thực hiện cho mọi ID mà nguồn có thể phát”.

Cũng không được suy ra rằng mọi overload nhận `Iterable` đều có một overload nhận `Publisher` tương ứng. Chẳng hạn, không tự giả định có `deleteAllById(Publisher<ID>)` trong hợp đồng Commons chỉ vì `findAllById` có dạng publisher.

Khi mở rộng repository hoặc dùng query method riêng, chữ ký được hỗ trợ và cách binding publisher phải kiểm tra theo module store. Một tham số publisher không tự biến thành điều kiện SQL `IN`, cũng không tự yêu cầu chạy query một lần cho từng giá trị.

## 4. findById(Publisher) chỉ sử dụng ID đầu tiên

Ví dụ:

```java
Publisher<Long> ids = Flux.just(10L, 20L, 30L);

Mono<Product> result = repository.findById(ids);
```

Ý nghĩa là tìm theo ID đầu tiên, không phải tìm ba sản phẩm rồi lấy một sản phẩm trong số đó.

Một trường hợp dễ hiểu sai:

```text
Nguồn ID: 404, 10

ID 404 không tồn tại.
ID 10 tồn tại.
```

`findById(ids)` không phải thuật toán “thử từng ID cho đến khi có sản phẩm”. Khi ID đầu tiên là `404`, việc không tìm thấy sản phẩm không khiến phương thức tự chuyển sang ID `10`.

Nếu mục tiêu là tìm nhiều ID, dùng method thích hợp:

```java
Flux<Product> products = repository.findAllById(ids);
```

Nếu mục tiêu thật sự là thử theo thứ tự và lấy sản phẩm đầu tiên tìm thấy, có thể biểu diễn rõ bằng composition:

```java
Mono<Product> firstExisting = Flux.from(ids)
        .concatMap(repository::findById)
        .next();
```

Ở đây, nguồn được chuyển thành các lần tìm theo từng ID; `next()` chọn phần tử kết quả đầu tiên. Đây là một thuật toán khác với overload `findById(Publisher)`, có chi phí và đặc tính cancellation riêng.

Không đặt một tác dụng phụ bắt buộc vào các phần tử phía sau của nguồn ID rồi truyền nguồn đó cho method chỉ cần một ID. Nguồn có thể bị hủy khi đã cung cấp giá trị cần thiết.

## 5. Mono.from chọn phần tử đầu tiên, không kiểm tra đúng một phần tử

Một mẫu composition thường dùng:

```java
Mono<Product> result = Mono.from(idSource)
        .flatMap(repository::findById);
```

`Mono.from(...)` thích nghi nguồn về không hoặc một phần tử bằng cách lấy phần tử đầu tiên. Nó không xác minh rằng nguồn ban đầu chỉ có đúng một phần tử.

Nếu hợp đồng nghiệp vụ yêu cầu nguồn phải có đúng một ID, hãy mô hình hóa yêu cầu đó:

```java
Mono<Long> exactlyOneId = Flux.from(idSource)
        .singleOrEmpty()
        .switchIfEmpty(Mono.error(
                new IllegalArgumentException(
                        "Exactly one identifier is required"
                )
        ));
```

Trong mẫu này:

- Không có ID: chuyển thành lỗi thiếu đầu vào.
- Có một ID và nguồn hoàn tất: chấp nhận.
- Có nhiều hơn một ID: lỗi cardinality từ `singleOrEmpty`.

Việc kiểm tra chỉ có một phần tử cần quan sát đủ nguồn để xác nhận. Một nguồn phát một ID rồi không bao giờ hoàn tất có thể khiến bước kiểm tra tiếp tục chờ. Nguồn tham số cho yêu cầu “đúng một ID” cần có vòng đời phù hợp.

Nếu API chỉ cam kết dùng ID đầu tiên, không cần thêm kiểm tra cardinality trái với hợp đồng đó. Điều quan trọng là đặt tên và tài liệu hóa đúng chính sách.

## 6. Rỗng ở đầu vào khác với không tìm thấy ở đầu ra

Xét hai tình huống:

```text
A. Nguồn ID hoàn tất mà không phát ID nào.
B. Nguồn ID phát 10, nhưng store không có sản phẩm 10.
```

Cả hai có thể dẫn đến một pipeline hoàn tất không có sản phẩm, nhưng nguyên nhân nghiệp vụ khác nhau.

| Tình huống | Câu hỏi cần giải quyết |
|---|---|
| Không có ID | Request có thiếu dữ liệu bắt buộc không? |
| Có ID nhưng không có entity | Có báo không tìm thấy hay giữ kết quả rỗng không? |
| Nguồn ID lỗi | Lỗi lấy tham số cần được truyền hay ánh xạ thế nào? |
| Store lỗi | Có cần retry hoặc ánh xạ lỗi hạ tầng không? |

Một mẫu xử lý rõ hai mức:

```java
Mono<Product> result = Mono.from(idSource)
        .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Identifier is required")
        ))
        .flatMap(id -> repository.findById(id)
                .switchIfEmpty(Mono.error(
                        new NoSuchElementException(
                                "Product not found: " + id
                        )
                )));
```

`switchIfEmpty` thứ nhất áp dụng cho nguồn ID. `switchIfEmpty` thứ hai áp dụng cho kết quả tìm theo một ID đã có.

Nếu chỉ đặt một fallback ở cuối toàn bộ pipeline, ứng dụng có thể làm mất khả năng phân biệt “không có ID” với “không có bản ghi”.

`switchIfEmpty` chỉ phản ứng với completion không có phần tử. Nó không bắt lỗi; lỗi từ nguồn ID hoặc database vẫn được truyền nếu không có operator xử lý lỗi riêng.

## 7. Mono<Boolean>: false là một giá trị, không phải kết quả rỗng

Khi một phép kiểm tra tồn tại thực sự được thực hiện, giá trị `false` có nghĩa là kết quả kiểm tra âm:

```text
onNext(false) -> onComplete
```

Nó khác với:

```text
onComplete
```

Kiểu `Mono<Boolean>` về mặt cardinality vẫn cho phép không có phần tử. Đặc biệt, đừng suy rằng truyền một nguồn ID rỗng sẽ tự động có cùng ý nghĩa với kiểm tra một ID không tồn tại.

Có thể thấy sự khác biệt qua một pipeline composition:

```java
Mono<Boolean> exists = Mono.from(idSource)
        .flatMap(repository::existsById);
```

Nếu `idSource` rỗng, `flatMap` không nhận ID để gọi phép kiểm tra. Pipeline này hoàn tất rỗng, không tự phát `false`.

Với overload trực tiếp của repository, cần đối chiếu hợp đồng và hành vi của module đang dùng khi nguồn tham số rỗng. Một cách thiết kế ổn định ở lớp ứng dụng là chọn chính sách trước khi gọi store.

### Chính sách 1: thiếu ID là lỗi

```java
Mono<Boolean> exists = Mono.from(idSource)
        .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Identifier is required")
        ))
        .flatMap(repository::existsById);
```

### Chính sách 2: thiếu ID được quy về false

```java
Mono<Boolean> existsOrFalse = Mono.from(idSource)
        .flatMap(repository::existsById)
        .defaultIfEmpty(false);
```

Đây là quyết định nghiệp vụ của pipeline, không phải một quy tắc rằng mọi publisher rỗng đều phải đổi thành `false`.

Nếu nguồn phát lỗi, `defaultIfEmpty(false)` không nuốt lỗi đó. Một fallback như `onErrorReturn(false)` lại có ý nghĩa khác và có thể che việc database không truy cập được thành “không tồn tại”.

## 8. Mono<Void> biểu diễn completion, không biểu diễn entity bị thiếu

Một thao tác xóa thường trả:

```java
Mono<Void> deletion = repository.deleteById(id);
```

Khi hoàn tất bình thường, nó không phát giá trị qua `onNext`. Chính sự vắng mặt của phần tử là hình dạng thành công của thao tác, không phải bằng chứng “không tìm thấy để xóa”.

| Cách xử lý | Ý nghĩa thực tế với `Mono<Void>` |
|---|---|
| `map(value -> true)` | Không có phần tử để gọi hàm |
| `doOnNext(...)` | Không được gọi trong completion thành công không có giá trị |
| `thenReturn(true)` | Phát `true` sau completion thành công |
| `hasElement()` | Không có phần tử dữ liệu để báo có |
| `switchIfEmpty(fallback)` | Fallback được chọn khi nguồn hoàn tất bình thường không có giá trị |

### 8.1. Không dùng switchIfEmpty sau delete để suy ra not found

Cách dễ sai:

```java
repository.deleteById(id)
        .switchIfEmpty(Mono.error(
                new NoSuchElementException("Product not found")
        ));
```

Một lần xóa hoàn tất thành công vẫn là một `Mono<Void>` không có phần tử. Vì vậy fallback có thể biến chính completion thành công thành lỗi.

Tương tự, cách sau cũng sai mục tiêu:

```java
repository.findById(id)
        .flatMap(repository::delete)
        .switchIfEmpty(Mono.error(
                new NoSuchElementException("Product not found")
        ));
```

Sau `flatMap(repository::delete)`, dữ liệu entity đã được thay bằng completion của thao tác xóa. Không thể dùng trạng thái không có phần tử ở vị trí đó để phân biệt có tìm thấy entity trước đó hay không.

Cần xử lý rỗng trước khi chuyển sang thao tác trả `Mono<Void>`:

```java
Mono<Void> deletion = repository.findById(id)
        .switchIfEmpty(Mono.error(
                new NoSuchElementException("Product not found")
        ))
        .flatMap(repository::delete);
```

Đường đọc rồi xóa này kiểm tra sự tồn tại tại thời điểm đọc. Nó không tự bảo đảm số hàng bị xóa nếu có thao tác cạnh tranh; yêu cầu đó cần cơ chế nhất quán hoặc API có hợp đồng số hàng ảnh hưởng phù hợp với store.

### 8.2. thenReturn chỉ xác nhận completion theo hợp đồng thao tác

```java
Mono<String> response = repository.deleteById(id)
        .thenReturn("Deletion operation completed");
```

Chuỗi chỉ phát thông báo sau completion bình thường. Nó không tự chứng minh một hàng đã tồn tại hoặc chính xác một hàng bị xóa.

Không dùng `defaultIfEmpty(null)` để tạo dữ liệu cho `Mono<Void>`. Reactor không dùng `null` làm một phần tử tín hiệu hợp lệ.

## 9. Các nguồn rỗng với method xử lý nhiều phần tử

Với nguồn hữu hạn không có phần tử:

```java
Publisher<Long> noIds = Flux.empty();
Publisher<Product> noProducts = Flux.empty();
```

Cần phân biệt rõ từng overload:

| Lời gọi | Ý nghĩa đầu vào |
|---|---|
| `findAllById(noIds)` | Không cung cấp ID nào để tìm |
| `saveAll(noProducts)` | Không cung cấp entity nào để lưu |
| `deleteAll(noProducts)` | Không cung cấp entity nào để xóa |
| `deleteAll()` | Yêu cầu xóa toàn bộ theo hợp đồng của method không đối số |

Truyền một publisher entity rỗng vào `deleteAll(Publisher)` không tương đương với gọi `deleteAll()`. Việc chọn overload đúng là một phần của hợp đồng, không phải một chi tiết cú pháp.

Kết quả thường cần hiểu theo hình dạng:

- Một thao tác đọc nhiều không có entity trả về là `Flux` hoàn tất rỗng.
- Một thao tác lưu nguồn rỗng không phát entity đã lưu.
- Một thao tác xóa nguồn entity rỗng có completion mà không có giá trị kết quả.
- Lỗi của nguồn đầu vào vẫn khác với completion rỗng.

Không dùng `switchIfEmpty(repository.findAll())` chỉ để “xử lý đẹp” một danh sách ID rỗng nếu điều đó vô tình đổi yêu cầu không có ID thành truy vấn toàn bộ dữ liệu. Chỉ thêm fallback mở rộng phạm vi khi nghiệp vụ thật sự yêu cầu.

Một nguồn phát một số entity rồi lỗi cũng không giống nguồn rỗng. Có thể đã có thao tác ghi được thực hiện trước lỗi. Việc rollback cần transaction phù hợp, không tự xuất hiện nhờ kiểu tham số publisher.

## 10. Tìm nhiều ID không bảo đảm một kết quả cho mỗi ID

`findAllById` trả các entity được tìm thấy. Không nên mặc định:

- Mọi ID đầu vào đều tồn tại.
- Số entity kết quả bằng số ID đầu vào.
- Kết quả giữ nguyên thứ tự đầu vào.
- ID lặp tạo ra số lần phát entity lặp giống hệt.
- Implementation chạy một query độc lập cho từng ID.

Store có thể nhóm hoặc đệm ID để thực hiện truy vấn. Publisher đầu vào không tự bảo đảm khả năng xử lý một nguồn ID vô hạn theo cách streaming từng phần. Một implementation cần thu thập đầu vào hữu hạn có thể chờ nguồn hoàn tất trước bước truy vấn tương ứng.

Nếu API cần kết quả cho từng ID theo đúng thứ tự, hãy biểu diễn rõ. Ví dụ:

```java
import java.util.Optional;

public record ProductLookup(
        Long requestedId,
        Optional<Product> product
) {
}
```

Pipeline:

```java
Flux<ProductLookup> lookups = Flux.from(idSource)
        .concatMap(id -> repository.findById(id)
                .map(product -> new ProductLookup(
                        id,
                        Optional.of(product)
                ))
                .defaultIfEmpty(new ProductLookup(
                        id,
                        Optional.empty()
                )));
```

Mỗi ID được xử lý ở đây cho ra một `ProductLookup`: tìm thấy hoặc không tìm thấy. `Optional.empty()` là dữ liệu nằm trong wrapper, không phải một phần tử `null`.

Mẫu này có thể tạo nhiều query hơn `findAllById`. Nó phù hợp khi yêu cầu kết quả theo từng ID quan trọng hơn chiến lược truy vấn gộp. Việc chọn `concatMap` thể hiện xử lý tuần tự theo nguồn; không dùng `flatMap` rồi mặc định thứ tự hoàn tất được giữ nguyên.

Không cần bọc mọi kết quả repository bằng `Mono<Optional<T>>`. Wrapper chỉ hữu ích khi ứng dụng muốn sự vắng mặt trở thành dữ liệu có thể mang thêm ngữ cảnh.

## 11. Xóa theo một luồng ID phải được biểu diễn rõ

Nếu muốn xóa theo mọi ID trong nguồn, đừng truyền cả `Flux<ID>` cho overload chỉ dùng ID đầu tiên.

Một composition có thể dùng:

```java
Mono<Void> deleteAllRequested = Flux.from(idSource)
        .concatMap(repository::deleteById)
        .then();
```

Ở đây:

1. Mỗi ID tạo một thao tác `deleteById(ID)`.
2. `concatMap` kết hợp các thao tác theo thứ tự nguồn.
3. `then()` chuyển toàn bộ chuỗi thành completion cuối cùng.

Kết quả không cung cấp số hàng bị xóa. Khi một bước lỗi, pipeline cũng không tự bảo đảm những bước đã thực hiện trước đó được rollback.

Nếu cần transaction cho cả luồng, phải dùng cơ chế transaction reactive phù hợp với store. Nếu cần hiệu năng của một lệnh xóa theo tập ID, có thể cần query hoặc API riêng của store với hợp đồng kết quả rõ ràng.

Với các derived query có tham số vô hướng, cách kết hợp cũng nên tường minh. Giả sử repository hỗ trợ:

```java
Flux<Product> findByCategory(String category);
```

Một nguồn cung cấp một category có thể được nối như sau:

```java
Flux<Product> products = Mono.from(categorySource)
        .flatMapMany(repository::findByCategory);
```

Nguồn category rỗng làm pipeline này không gọi query. Nếu muốn xử lý nhiều category, phải mô tả việc lặp và kết hợp kết quả, thay vì mặc định method sẽ tự làm điều đó khi đổi tham số sang publisher.

## 12. Ví dụ R2DBC: service chọn rõ chính sách rỗng

Ví dụ mapping:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("product")
public record Product(
        @Id Long id,
        String name,
        String category
) {
}
```

Repository:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {
}
```

Mỗi kiểu public là một đơn vị mã nguồn riêng. Ứng dụng cần schema, connection factory và cấu hình R2DBC phù hợp. Commons cung cấp hợp đồng repository, không tự cung cấp một kết nối database.

Service:

```java
import java.util.NoSuchElementException;

import org.reactivestreams.Publisher;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ProductLookupService {

    private final ProductRepository repository;

    public ProductLookupService(ProductRepository repository) {
        this.repository = repository;
    }

    public Mono<Product> findRequired(Publisher<Long> idSource) {
        return requireFirstId(idSource)
                .flatMap(id -> repository.findById(id)
                        .switchIfEmpty(Mono.error(
                                new NoSuchElementException(
                                        "Product not found: " + id
                                )
                        )));
    }

    public Mono<Boolean> existsForRequiredId(
            Publisher<Long> idSource
    ) {
        return requireFirstId(idSource)
                .flatMap(repository::existsById);
    }

    public Mono<Void> deleteRequired(Publisher<Long> idSource) {
        return findRequired(idSource)
                .flatMap(repository::delete);
    }

    private Mono<Long> requireFirstId(
            Publisher<Long> idSource
    ) {
        if (idSource == null) {
            return Mono.error(new IllegalArgumentException(
                    "Identifier publisher must not be null"
            ));
        }

        return Mono.from(idSource)
                .switchIfEmpty(Mono.error(
                        new IllegalArgumentException(
                                "Identifier is required"
                        )
                ));
    }
}
```

Chính sách của service là:

| Tình huống | Kết quả |
|---|---|
| Tham số publisher là `null` | Lỗi đầu vào |
| Publisher hợp lệ nhưng không phát ID | Lỗi thiếu ID |
| Publisher phát nhiều ID | Dùng ID đầu tiên theo tên helper |
| Có ID nhưng không có sản phẩm khi đọc bắt buộc | Lỗi không tìm thấy |
| Kiểm tra một ID không tồn tại | Giá trị `false` từ phép kiểm tra tồn tại |
| Xóa sau khi đã tìm thấy | `Mono<Void>` hoàn tất hoặc lỗi |

Service trả pipeline cho bên gọi, không tự subscribe để tách công việc ra một luồng riêng. Việc ánh xạ lỗi thành HTTP response hoặc kết quả tác vụ thuộc lớp biên của ứng dụng.

Ví dụ chưa bổ sung một chính sách transaction hay khóa cho bước đọc rồi xóa. Nếu yêu cầu nghiệp vụ cần tính nhất quán giữa các bước, phải bổ sung bằng khả năng của store.

## 13. Vị trí operator quyết định ý nghĩa của rỗng

Một operator xử lý rỗng chỉ thấy đoạn pipeline phía trước nó.

| Vị trí | Rỗng có thể mang ý nghĩa |
|---|---|
| Sau nguồn ID | Không nhận được tham số |
| Sau `findById` | Không có entity phù hợp |
| Sau `filter` | Có dữ liệu nhưng bị loại theo điều kiện |
| Sau `flatMap` sang `Mono<Void>` | Hoàn tất thao tác không có giá trị |
| Sau `then()` | Dữ liệu trước đó đã được chủ động bỏ đi |

Ví dụ:

```java
repository.findById(id)
        .filter(product -> "BOOK".equals(product.category()))
        .switchIfEmpty(Mono.error(
                new NoSuchElementException("No matching product")
        ));
```

Fallback không chỉ có nghĩa là ID không tồn tại. Nó còn có thể được chọn vì sản phẩm tồn tại nhưng category không phù hợp.

Nếu hai tình huống cần lỗi khác nhau, xử lý kết quả tìm trước rồi áp dụng kiểm tra nghiệp vụ riêng.

### zip và các nguồn rỗng

`zip` cần phần tử từ các nguồn để tạo kết quả ghép. Một nguồn hoàn tất rỗng khiến không có đủ dữ liệu để tạo tuple; cũng không nên dựa vào `zip` để bảo đảm mọi tác dụng phụ đều được subscribe và thực thi khi có nguồn rỗng.

Đặc biệt, `Mono<Void>` không cung cấp một giá trị `Void` để ghép. Nếu mục tiêu là nối bước sau khi một thao tác hoàn tất, dùng `then`. Nếu mục tiêu là phối hợp completion của nhiều nguồn, chọn operator có hợp đồng completion phù hợp.

### collectList biến rỗng thành một giá trị collection

```java
Mono<List<Product>> list = repository.findAllById(idSource)
        .collectList();
```

Nếu upstream hoàn tất không có entity, kết quả là một list rỗng được phát như một giá trị. Vì vậy, `switchIfEmpty` đặt sau `collectList()` không dùng để phát hiện list có kích thước bằng không.

Nếu cần chính sách riêng cho list rỗng, kiểm tra nội dung list. Đồng thời nhớ rằng `collectList()` gom dữ liệu vào bộ nhớ và chờ upstream hoàn tất.

## 14. Error, cancellation và subscription lại không phải rỗng

### 14.1. Error không phải completion rỗng

```java
Mono<Product> result = repository.findById(id)
        .switchIfEmpty(Mono.error(
                new NoSuchElementException("Product not found")
        ));
```

Lỗi database không đi vào fallback của `switchIfEmpty`. Đây là hành vi cần giữ nếu không muốn “không tìm thấy” che khuất một sự cố hạ tầng.

Một `onErrorResume(error -> Mono.empty())` quá rộng có thể làm lỗi thật bị biến thành rỗng, rồi bị một fallback phía sau diễn giải thành sai nguyên nhân.

### 14.2. Cancellation không phải hoàn tất thành công

Khi bên sử dụng hủy subscription, nguồn có thể ngừng cung cấp ID hoặc kết quả. Không suy rằng cancellation tương đương `onComplete`, cũng không suy rằng mọi thao tác database đã được hoàn tác.

Đối với method dùng ID đầu tiên, đừng đặt logic bắt buộc ở phần còn lại của nguồn ID. Sau khi có ID cần dùng, nguồn không còn được kỳ vọng sẽ bị tiêu thụ hết.

### 14.3. Subscription lại có thể đọc tham số và thực hiện thao tác lại

Nếu nguồn tham số là cold, subscription mới có thể tạo ID hoặc dữ liệu mới. Nếu publisher kết quả được subscribe nhiều lần hoặc có retry, đường lấy tham số và truy cập store có thể được thực hiện lại.

Với thao tác ghi, điều đó có thể gây tác dụng phụ lặp. Không coi việc tham số có kiểu `Mono` là bằng chứng giá trị đã được chụp một lần và dùng lại mãi mãi.

Nguồn hot còn có thể phát trước khi repository subscribe, tùy đặc tính của nguồn. Chọn nguồn tham số có vòng đời rõ ràng cho request, thay vì dùng bất kỳ luồng sự kiện chia sẻ nào như một biến ID.

## 15. Xác minh tín hiệu bằng những kịch bản đúng trọng tâm

Reactor Test có thể kiểm tra các nguyên tắc nền mà không cần database.

### 15.1. Chọn ID đầu tiên

```java
StepVerifier.create(
        Mono.from(Flux.just(10L, 20L))
)
        .expectNext(10L)
        .verifyComplete();
```

Đây là kiểm tra semantics của `Mono.from`, không thay thế kiểm tra tích hợp overload repository.

### 15.2. false là dữ liệu

```java
StepVerifier.create(
        Mono.just(false).defaultIfEmpty(true)
)
        .expectNext(false)
        .verifyComplete();
```

Fallback không chạy vì nguồn đã phát một phần tử, dù phần tử đó có giá trị `false`.

### 15.3. Mono<Void> hoàn tất rỗng

```java
StepVerifier.create(
        Mono.<Void>empty()
                .switchIfEmpty(Mono.error(
                        new IllegalStateException(
                                "Fallback was selected"
                        )
                ))
)
        .expectError(IllegalStateException.class)
        .verify();
```

Ví dụ giải thích vì sao không dùng `switchIfEmpty` phía sau một thao tác xóa trả `Mono<Void>` để suy ra not found.

Khi dùng các ví dụ trên, import:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
```

Với repository thật, cần kiểm tra thêm bằng module store và dữ liệu được chuẩn bị rõ ràng:

| Kịch bản | Điều cần xác minh |
|---|---|
| Publisher phát một ID tồn tại | Entity tương ứng được trả về |
| Publisher phát một ID không tồn tại | Kết quả không có entity theo hợp đồng query |
| Publisher phát nhiều ID cho `findById` | Không biến thành truy vấn cho mọi ID |
| ID đầu tiên không tồn tại, ID sau tồn tại | Không tự tìm tiếp đến khi gặp entity |
| Publisher ID rỗng | Chính sách đầu vào ở service được áp dụng |
| `findAllById` có ID không tồn tại | Không giả định số kết quả bằng số ID |
| `deleteAll(Publisher)` nhận nguồn rỗng | Không bị nhầm với `deleteAll()` không đối số |
| Nguồn ID lỗi | Lỗi không bị diễn giải thành thiếu tham số |
| Thao tác xóa hoàn tất | Không chờ một phần tử `Void` |
| Stream ghi lỗi giữa chừng | Chính sách transaction và retry đúng thiết kế |

Không chỉ mock một giá trị `Mono` rồi kết luận module xử lý mọi overload giống nhau. Kiểm tra tích hợp cần xác minh đường repository thực tế.

## 16. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần xem xét |
|---|---|
| Truyền nhiều ID nhưng chỉ xử lý một ID | Đang dùng overload chỉ lấy phần tử đầu tiên |
| ID thứ nhất không có dữ liệu dù ID sau có | Nhầm `findById(Publisher)` với thuật toán tìm phần tử tồn tại đầu tiên |
| `Mono<Boolean>` không gọi `map` | Nguồn ID hoặc đoạn upstream đã hoàn tất rỗng |
| Xóa thành công lại báo not found | Đặt `switchIfEmpty` sau `Mono<Void>` |
| Không nhận `true` từ `map` sau delete | Không có phần tử dữ liệu để map |
| Query nhiều ID thiếu kết quả | Có ID không tồn tại; không có cam kết một kết quả cho mỗi ID |
| Query nhận list rỗng lại đọc toàn bộ bảng | Fallback đã mở rộng phạm vi ngoài ý nghĩa ban đầu |
| `switchIfEmpty` không chạy sau `collectList` | List rỗng vẫn là một phần tử kết quả |
| Chỉ sai khi nguồn không hoàn tất | Operator hoặc implementation cần completion để xử lý đủ đầu vào |
| Lỗi hạ tầng bị báo thành không tìm thấy | Có xử lý lỗi quá rộng đã biến lỗi thành rỗng |
| Hành vi đổi khi thay store | Đã suy rộng khả năng binding hoặc buffering của một module |

## 17. Bài thực hành

Với một repository reactive được hỗ trợ bởi store đã chọn:

1. Tạo ba nguồn ID: một phần tử, nhiều phần tử và rỗng.
2. So sánh `findById(Publisher)` với `findAllById(Publisher)`.
3. Chọn rõ chính sách thiếu ID là lỗi hay kết quả hợp lệ.
4. Phân biệt thiếu ID với có ID nhưng không có entity.
5. Viết phép kiểm tra tồn tại mà không nhầm `false` với rỗng.
6. Viết thao tác xóa bắt buộc tìm thấy entity, đặt xử lý rỗng trước bước delete.
7. Thử nguồn entity rỗng cho `deleteAll(Publisher)` và giải thích vì sao khác method không đối số.
8. Nếu cần một kết quả cho từng ID, thiết kế wrapper mang cả ID yêu cầu và trạng thái tìm thấy.

Điểm cần giải thích được là: **hợp đồng method quyết định cách tiêu thụ Publisher đầu vào; vị trí operator quyết định ý nghĩa của rỗng; Mono<Void> dùng completion làm kết quả thành công, còn false vẫn là một giá trị dữ liệu**. Các khả năng về query, transaction và thực thi theo luồng phải được áp dụng theo đúng module store.