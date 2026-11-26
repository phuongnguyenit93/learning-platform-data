# Thiết kế hợp đồng phân trang cho ứng dụng mà không che chi phí truy vấn

Một hợp đồng phân trang không chỉ mô tả danh sách và số trang. Khi hứa cung cấp tổng số chính xác, cho phép nhảy tới trang rất sâu hoặc trả entity có nhiều quan hệ, ứng dụng đang nhận thêm nghĩa vụ truy vấn. Nếu mọi use case đều dùng một hàm chung trả `Page<T>`, các nghĩa vụ đó dễ bị che sau một interface gọn nhưng đắt hơn nhu cầu thật.

Trong chương **Phân trang** của **SPRING_DATA_COMMONS**, bài này đi từ yêu cầu của caller đến kiểu kết quả, tham số, metadata và khả năng thực thi của store. Mục tiêu là tạo hợp đồng rõ ràng về điều ứng dụng cung cấp, đồng thời giữ chi phí count, offset, sort, mapping và tải quan hệ có thể được nhận diện và đo lường.

## 1. Bắt đầu bằng thông tin caller thật sự cần

Trước khi chọn `Page`, cần trả lời:

1. Caller có cần tổng số kết quả và tổng số trang không?
2. Caller cần nhảy tới một trang tùy ý hay chỉ đi tiếp?
3. Dữ liệu có thay đổi trong lúc người dùng duyệt không?
4. Mỗi phần tử cần những trường nào?
5. Store và loại truy vấn đang dùng hỗ trợ hình dạng truy cập nào?

| Nhu cầu | Hợp đồng khởi đầu phù hợp | Nghĩa vụ cần nhìn thấy |
| --- | --- | --- |
| Bảng quản trị cần tổng số và số trang | `Page` theo khả năng module | Có metadata tổng, có thể cần count riêng |
| Danh sách chỉ có nút xem tiếp | `Slice` hoặc một hợp đồng tiếp tục tương ứng | Cần xác định còn kết quả, không cần tổng chính xác |
| Feed tiếp tục từ mốc đã đọc | `Window`/cursor nếu module hỗ trợ | Quản lý vị trí, sort và điều kiện tiếp tục |
| Export hoặc xử lý nhiều dữ liệu | Cơ chế duyệt có checkpoint và mức nhất quán phù hợp | Không chỉ là một page size lớn |
| Màn hình chỉ cần tổng khi người dùng yêu cầu | Luồng nội dung và thao tác lấy tổng được thiết kế riêng | Count là một khả năng được gọi có chủ đích |

Không cần công bố chi tiết SQL trong trải nghiệm người dùng để làm chi phí rõ ràng. Hợp đồng sản phẩm cần nói đúng khả năng: có tổng hay không, có thể nhảy trang hay chỉ tiếp tục, giới hạn kích thước và mức mới của dữ liệu. Ở tầng kỹ thuật, những khả năng đó phải được nối với cơ chế truy vấn và quan sát thực thi tương ứng.

## 2. Một yêu cầu phân trang có nhiều nhóm chi phí

Có thể phân tích theo những thành phần sau:

| Nhóm chi phí | Ví dụ |
| --- | --- |
| Tìm và lấy nội dung | Predicate, join, chỉ mục, truy cập dữ liệu |
| Xác định vị trí | Bỏ qua offset sâu hoặc tạo điều kiện seek/keyset |
| Sắp xếp | Sort có được hỗ trợ bởi chỉ mục hoặc cần xử lý thêm |
| Tính tổng | Count đúng bộ lọc, distinct hoặc grouping |
| Ánh xạ kết quả | Tạo entity/projection, chuyển đổi kiểu |
| Tải quan hệ | Các truy vấn phát sinh khi đọc thuộc tính liên quan |
| Truyền và tuần tự hóa | Số trường, số phần tử, kích thước phản hồi |

Đây là các nhóm để phân tích và đo, không phải một công thức buộc thời gian luôn cộng tuần tự; một số công việc có thể chồng lấp tùy stack.

Page size nhỏ chỉ trực tiếp giới hạn nội dung mà hợp đồng muốn trả. Nó không tự giới hạn số hàng được store quét, chi phí count hay số lượt tải quan hệ.

Một phản hồi có hai mươi phần tử vẫn có thể đắt nếu count xử lý một tập lớn, offset nằm rất sâu hoặc mapper truy cập quan hệ gây thêm nhiều truy vấn.

## 3. Chọn kiểu kết quả trước khi viết abstraction chung

### 3.1. Page mang nghĩa vụ về tổng số

`Page<T>` cung cấp nội dung, vị trí trang và metadata như `totalElements`, `totalPages`. Module có thể cần truy vấn đếm riêng hoặc suy ra tổng trong một số trường hợp.

Không nên khẳng định mỗi `Page` luôn tạo đúng hai truy vấn. Nhưng cũng không nên nghĩ bỏ lời gọi `getTotalElements()` ở caller sẽ tự tránh được count: việc chọn query method trả `Page` đã giao cho hạ tầng nghĩa vụ tạo metadata tổng theo cách implementation thực hiện.

Nếu cuối cùng chỉ lấy `page.getContent()` để trả một feed không có tổng, ứng dụng có thể đã trả chi phí cho thông tin không sử dụng.

### 3.2. Slice tránh nghĩa vụ tổng, vẫn phải xác định tiếp tục

`Slice<T>` cung cấp nội dung và thông tin như `hasNext`, không có tổng số như `Page`. Cách thường gặp là lấy thêm một phần tử so với kích thước yêu cầu để xác định có phần sau.

Với size bằng `20`, backend có thể đọc thêm để biết còn kết quả rồi chỉ trả hai mươi phần tử nội dung. Không coi “không count” là “chỉ làm đúng hai mươi đơn vị công việc”.

Nếu Slice vẫn được truy cập bằng offset, trang sâu vẫn có chi phí xác định vị trí. Đổi kiểu trả về không tự chuyển query sang keyset.

### 3.3. Window gắn với scrolling, cần khả năng store

`Window<T>` cung cấp nội dung cửa sổ và vị trí tiếp tục. Nếu module hỗ trợ keyset, cách tiếp tục có thể dựa trên bộ khóa sort thay vì bỏ qua một offset lớn.

Tuy vậy, `Window` có thể liên quan offset scrolling hoặc keyset scrolling theo cơ chế thực tế. Không suy từ tên kiểu rằng backend đã dùng một cursor server-side, đã tránh mọi chi phí truy cập sâu hoặc đã tạo snapshot.

Không thể đổi mọi method trả `Page` thành `Window` chỉ bằng thay kiểu trả về. Tham số, giới hạn, nguồn truy vấn, sort và mapping phải thuộc những tổ hợp module hỗ trợ.

## 4. Công bố hai dạng phản hồi thay vì giấu tổng trong một danh sách

Ví dụ một API theo số trang, page index từ `0`, có tổng chính xác theo truy vấn đã thực hiện:

```json
{
  "items": [
    { "id": 842 },
    { "id": 841 }
  ],
  "page": 0,
  "size": 2,
  "returned": 2,
  "totalElements": 137,
  "totalPages": 69,
  "hasNext": true
}
```

Một API tiếp tục theo cursor có thể công bố:

```json
{
  "items": [
    { "id": 842 },
    { "id": 841 }
  ],
  "limit": 2,
  "returned": 2,
  "hasNext": true,
  "nextCursor": "opaque-cursor-token"
}
```

Token trong ví dụ chỉ minh họa một giá trị do ứng dụng định nghĩa, không phải định dạng mặc định của `ScrollPosition`.

Ở hợp đồng thứ hai, không có trường tổng số. Không điền `totalElements: 0` để biểu đạt “chưa tính tổng”, vì số không khẳng định một thông tin khác: toàn bộ tập không có kết quả.

Có thể thiết kế một DTO chung có trạng thái tổng rõ ràng, nhưng cần phân biệt ít nhất “đã cung cấp” và “không được cung cấp”. Đừng để một giá trị mặc định che việc count đã chạy, chưa chạy hay thất bại.

### Tổng ước lượng và tổng cũ cần tên gọi riêng

Nếu sản phẩm chấp nhận ước lượng hoặc cache count, phải công bố đúng tính chất của nó, chẳng hạn một trường riêng về ước lượng hoặc thời điểm quan sát. Không đặt một số gần đúng vào cùng hợp đồng “tổng chính xác” rồi coi việc các số không khớp là lỗi pagination ngẫu nhiên.

Đây là lựa chọn thiết kế bổ sung, không phải khả năng mà mọi repository tự cung cấp.

## 5. Quy định đầu vào và điều hướng

Một hợp đồng phân trang nên xác định rõ:

| Thành phần | Quyết định cần công bố |
| --- | --- |
| Chỉ số trang | Bắt đầu từ `0` hay `1` ở ranh giới API |
| Kích thước | Mặc định, khoảng được chấp nhận và cách xử lý vượt giới hạn |
| Sort | Các lựa chọn hợp lệ và thứ tự mặc định |
| Điểm tiếp tục | Page index, offset hay cursor |
| Vượt cuối dữ liệu | Trả nội dung rỗng, điều hướng lại hoặc báo theo hợp đồng |
| Thay bộ lọc/sort | Bắt đầu lại lượt duyệt hay có hành vi khác được định nghĩa |

Ví dụ ứng dụng chọn size từ `1` đến `100`. Đây là chính sách sản phẩm/kỹ thuật của ứng dụng, không phải trần cố định của Commons.

Nếu chọn từ chối yêu cầu quá lớn, hãy từ chối theo hợp đồng. Nếu chọn điều chỉnh size xuống giới hạn, phản hồi phải cho caller biết kích thước thực tế đã áp dụng, thay vì giữ một metadata không đúng với query.

`PageRequest` dùng index từ `0` và offset bằng page index nhân page size. Nếu API dùng số trang từ `1`, chuyển đổi ở một ranh giới đã chọn và không trừ lặp tại service khi web resolver đã xử lý.

Một giới hạn truy cập offset sâu cũng cần được đặt theo khả năng và yêu cầu của ứng dụng. Hợp đồng không nên hứa nhảy tới mọi trang tùy ý khi store hoặc ngân sách truy vấn không đáp ứng điều đó.

## 6. Sort xác định là một phần của hợp đồng tiếp tục

Giả sử domain `PurchaseOrder` có các thuộc tính `id`, `tenantId`, `status`, `createdAt`, `total`. Id duy nhất và `createdAt` không null ở dữ liệu đã lưu.

Ví dụ sort mặc định:

```java
import org.springframework.data.domain.Sort;

Sort newest = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"));
```

Khóa id phân định các đơn trùng thời điểm. Một danh sách chỉ sort theo `createdAt` chưa mô tả đầy đủ thứ tự trong nhóm bằng nhau.

Có thể công bố các lựa chọn nghiệp vụ rồi ánh xạ ở tầng ứng dụng:

| Lựa chọn | Bộ khóa nội bộ |
| --- | --- |
| Mới nhất | `createdAt DESC, id DESC` |
| Cũ nhất | `createdAt ASC, id ASC` |
| Giá trị cao nhất | `total DESC, id DESC` |

Sort theo một biểu thức tính toán hoặc một thuộc tính khó tận dụng chỉ mục có thể có chi phí khác với sort mặc định. Khả năng chấp nhận sort cần gắn với những query shape mà module/store hỗ trợ, không chỉ với việc caller gửi được tên field.

Cursor của một lượt duyệt phải được dùng cùng bộ lọc, tenant và bộ khóa tương ứng. Đổi sort hoặc filter nên bắt đầu một lượt duyệt mới theo hợp đồng đã chọn.

## 7. Ví dụ tách Page và Slice ở repository

Ví dụ dưới đây dùng **Spring Data JPA** với entity, mapping và hạ tầng đã được cấu hình phù hợp. DTO projection cần được module hỗ trợ và có constructor tương ứng các thuộc tính được chọn.

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderSummary(
        Long id,
        Instant createdAt,
        BigDecimal total) {
}
```

`OrderStatus` là enum nghiệp vụ, chẳng hạn `NEW`, `PAID`, `CANCELLED`.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.repository.Repository;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    Page<OrderSummary> findPageByTenantIdAndStatus(
            String tenantId,
            OrderStatus status,
            Pageable pageable);

    Slice<OrderSummary> findSliceByTenantIdAndStatus(
            String tenantId,
            OrderStatus status,
            Pageable pageable);
}
```

`Page` và `Slice` trước `By` là phần mô tả subject trong hai tên minh họa; kiểu trả về cùng implementation của module quyết định metadata kết quả.

Hai method cho phép use case lựa chọn hợp đồng có tổng hoặc chỉ có tiếp tục. Không cần luôn gọi method trả `Page` rồi xóa trường tổng khỏi phản hồi.

Ví dụ tạo request:

```java
Pageable request = PageRequest.of(0, 20, newest);
```

`Pageable` đã chứa size và sort. Không thêm một `Sort` riêng cùng một tham số `Pageable` để điều khiển trùng chức năng trong chữ ký chuẩn.

Projection được dùng để giới hạn hình dạng dữ liệu caller cần. Nó không tự bảo đảm query không join, không count hoặc không có chi phí mapping; những phần đó vẫn phải được quan sát theo query thực tế.

## 8. DTO ứng dụng giữ metadata đúng với lựa chọn

Một phản hồi theo số trang có thể được biểu đạt bằng Java record:

```java
import java.util.List;

public record NumberedResult<T>(
        List<T> items,
        int page,
        int size,
        int returned,
        long totalElements,
        int totalPages,
        boolean hasNext) {
}

public record SliceResult<T>(
        List<T> items,
        int page,
        int size,
        int returned,
        boolean hasNext) {
}
```

Đây là các khai báo độc lập cho từng kiểu, được trình bày cùng nhau để so sánh; khi đặt trong source Java cần tổ chức file/package theo quy tắc của Java.

Use case cần tổng:

```java
Page<OrderSummary> result = repository.findPageByTenantIdAndStatus(
        tenantId, status, request);

return new NumberedResult<>(
        result.getContent(),
        result.getNumber(),
        result.getSize(),
        result.getNumberOfElements(),
        result.getTotalElements(),
        result.getTotalPages(),
        result.hasNext());
```

Use case chỉ cần tiếp tục:

```java
Slice<OrderSummary> result = repository.findSliceByTenantIdAndStatus(
        tenantId, status, request);

return new SliceResult<>(
        result.getContent(),
        result.getNumber(),
        result.getSize(),
        result.getNumberOfElements(),
        result.hasNext());
```

DTO riêng giúp ứng dụng kiểm soát những trường được cam kết và không buộc caller phụ thuộc vào toàn bộ implementation của một container Spring Data.

Hai ví dụ không tạo một transaction chung cho mọi lần đọc trang. Chúng cũng không tự định nghĩa một giao thức cursor; nếu dùng Window, cần adapter khác cho vị trí tiếp tục và khả năng scrolling đã xác nhận.

## 9. Không xây abstraction chung buộc mọi consumer phải count

Một interface quá tổng quát như:

```java
Page<T> search(Criteria criteria, Pageable pageable);
```

có thể hợp lý nếu mọi consumer thật sự cần tổng. Nhưng nếu cùng interface phục vụ feed, export và bảng quản trị, nó đang áp đặt nghĩa vụ count lên nhiều use case khác nhau.

Có thể tổ chức các khả năng ở tầng query service theo nhu cầu:

- Tìm một trang cùng tổng cho bảng có số trang.
- Lấy phần tiếp theo không có tổng cho danh sách xem tiếp.
- Duyệt theo vị trí cho tác vụ hoặc feed mà store hỗ trợ scrolling.
- Tính tổng riêng khi sản phẩm yêu cầu rõ ràng.

Không nhất thiết tạo thật nhiều interface cho một tính năng nhỏ. Điều quan trọng là tên, kiểu trả về và đường thực thi phải giúp người bảo trì biết nơi nào yêu cầu tổng, nơi nào chỉ yêu cầu dữ liệu.

Nếu một store không hỗ trợ một khả năng, adapter không nên lén tải toàn bộ dữ liệu để giả lập rồi trình bày như một truy vấn phân trang rẻ. Cần chọn một implementation có chi phí phù hợp hoặc công bố giới hạn khả năng của use case.

## 10. Count là một truy vấn có ngữ nghĩa và ngân sách riêng

### 10.1. Count phải tương đương nội dung

Nếu nội dung lọc theo tenant, trạng thái và điều kiện nghiệp vụ, total phải đếm cùng tập đó. Không gọi một `count()` toàn repository để làm tổng cho một trang đã lọc.

Với join, grouping và distinct, cần xác định đơn vị đếm: entity gốc, dòng chi tiết hay nhóm kết quả. Một count nhanh nhưng đếm sai đơn vị không đáp ứng hợp đồng.

Trong Spring Data JPA, query khai báo phức tạp có thể cần `countQuery` riêng. Khả năng suy ra query đếm không đồng nghĩa mọi JPQL hoặc SQL native đều có phép đếm đúng và rẻ.

### 10.2. Lấy tổng riêng có thể là một chức năng riêng

Nếu người dùng hiếm khi cần tổng, có thể thiết kế thao tác lấy tổng độc lập hoặc một chế độ request tường minh. Khi đó các điều kiện sau phải được xác định:

- Cùng bộ lọc và phạm vi dữ liệu với nội dung đang quan sát.
- Thời điểm và mức mới mà tổng đại diện.
- Cách phản hồi khi count không thực hiện được.
- Có cho phép cache hoặc ước lượng không, và cách công bố tính chất đó.

Một tổng lấy riêng sau đó không tự là tổng của snapshot mà danh sách trước đó đã đọc. Không ghép hai số liệu cách nhau theo thời gian rồi hứa một tính nhất quán chưa được triển khai.

### 10.3. Cache tổng cần giữ đúng hợp đồng

Cache count theo sai tenant hoặc thiếu một filter có thể trả metadata sai dù query nội dung đúng. Cache cũ cũng cần được hiểu như dữ liệu có độ trễ, không phải một cách làm count chính xác tức thời miễn phí.

Nếu ứng dụng dùng số liệu cũ để hỗ trợ hiển thị, hợp đồng nên nói đúng độ mới được cung cấp. Không dùng sự bất nhất giữa nội dung và total để âm thầm che một count query sai.

## 11. Nhìn thấy chi phí phía sau entity và projection

### 11.1. Nhiều truy vấn có thể phát sinh sau khi repository trả kết quả

Một method lấy Page entity có thể hoàn tất, nhưng mapper DTO hoặc quá trình tuần tự hóa lại truy cập các quan hệ liên quan. Tùy mapping và fetch strategy, điều này có thể gây thêm nhiều truy vấn.

Vì vậy, chỉ đếm câu lệnh trong thời gian thực thi method repository có thể chưa phản ánh chi phí đầy đủ của endpoint. Cần xem cả việc tạo response mà use case thực hiện.

Projection có thể giúp giảm các trường cần tải nếu truy vấn/module hỗ trợ. Nhưng projection lồng nhau hoặc lựa chọn trường quan hệ vẫn có thể cần join và công việc bổ sung; không coi tên DTO là bằng chứng đủ cho hiệu năng.

### 11.2. Fetch join không phải thuốc chữa chung cho pagination

Một join quan hệ một-nhiều có thể tạo nhiều dòng trung gian cho một entity gốc. Kết hợp fetch, distinct, limit và count cần được đánh giá theo JPA provider, query shape và phiên bản đang dùng.

Không thay một vấn đề truy vấn bổ sung bằng một query fetch phức tạp rồi mặc định page size, số entity và tổng số vẫn đúng. Hợp đồng kết quả phải được kiểm chứng cùng hình dạng SQL/thao tác store thực tế.

### 11.3. Không post-filter một trang rồi công bố tổng của tập khác

Nếu service lấy hai mươi entity rồi bỏ mười lăm theo một điều kiện nghiệp vụ, phản hồi còn năm phần tử nhưng total có thể vẫn đếm tập gốc. Một trang bị lọc hết cũng không chứng minh toàn bộ truy vấn không có dữ liệu.

Nếu điều kiện thuộc bộ lọc phân trang, nên đưa nó vào cơ chế truy vấn phù hợp. Nếu cố ý post-filter, cần công bố đúng đơn vị và ngữ nghĩa metadata; không điền một total mới chỉ từ nội dung trang hiện tại.

## 12. Offset sâu, cursor và khả năng điều hướng

Một hợp đồng cho nhảy đến trang `50000` với size `20` có thể yêu cầu offset `1000000`. Dù phản hồi chỉ có hai mươi phần tử, store có thể phải xử lý nhiều dữ liệu để tới vị trí đó.

Nếu ứng dụng cần nhảy trang tùy ý, chi phí này phải nằm trong thiết kế và đo lường. Nếu sản phẩm chỉ cần đi tiếp, cursor/keyset có thể phù hợp hơn khi module hỗ trợ.

Đổi sang cursor cũng thay đổi khả năng sản phẩm:

| Điều hướng | Thông tin cần có | Giới hạn cần hiểu |
| --- | --- | --- |
| Nhảy đến page index tùy ý | Page index, size, sort | Có thể gặp offset sâu và cần tổng nếu hiển thị số trang |
| Đi tiếp theo cursor | Token hợp lệ cùng bộ lọc/sort | Không tự có khả năng nhảy tới một trang số bất kỳ |
| Duyệt tác vụ có checkpoint | Vị trí và chính sách khôi phục | Cần xử lý lỗi, cập nhật dữ liệu và khả năng chạy lại |

Một cursor không phải phiên bản mã hóa của một số offset theo mọi implementation. Cũng không phải mọi cursor đều cho lợi ích keyset. Cần xác nhận thuật toán phía sau adapter.

Nếu dùng keyset với projection, kết quả phải có các khóa cần trích xuất vị trí theo yêu cầu module. Token cũ không nên được dùng cho một sort hoặc phạm vi tenant khác.

## 13. Công bố mức nhất quán mà ứng dụng thật sự cung cấp

Một total được tính chính xác theo predicate tại lúc count không đồng nghĩa nội dung và total cùng thuộc một snapshot. Insert/delete/update giữa các lần đọc có thể làm trang sau lặp, thiếu hoặc trở nên rỗng.

Các mức nhu cầu khác nhau:

- Danh sách tương tác có thể chấp nhận dữ liệu mới theo từng request.
- Một báo cáo có thể cần mốc thời gian hoặc snapshot được xác định.
- Một tác vụ xử lý cần checkpoint và chính sách idempotency để tiếp tục sau lỗi.

Sort đầy đủ giải quyết thứ tự giữa các giá trị bằng nhau. Keyset giúp tiếp tục theo mốc. Transaction hoặc cơ chế snapshot giải quyết một phần bài toán phiên bản dữ liệu theo khả năng store. Không dùng một trong các cơ chế đó để hứa thay cho tất cả.

Nếu page cuối biến mất sau khi xóa, ứng dụng có thể điều hướng lại theo chính sách hoặc trả nội dung rỗng cùng metadata hiện có. Đừng thay một trang vượt phạm vi có total dương bằng `Page.empty(...)`, vì factory đó công bố tổng bằng không.

## 14. Lỗi và suy giảm chức năng không được giả làm kết quả rỗng

Count thất bại, query nội dung lỗi và không có entity là ba trạng thái khác nhau. Một mẫu bắt mọi exception rồi trả một page tổng bằng không làm hợp đồng có vẻ thành công trong khi dữ liệu chưa được đọc đúng.

Nếu sản phẩm cho phép trả nội dung khi tổng tạm thời không cung cấp được, khả năng đó phải được thiết kế tường minh trong DTO và đường xử lý. Nó không còn là cùng một lời hứa luôn có total chính xác của một Page bình thường.

Một giới hạn kỹ thuật của backend, chẳng hạn truy cập quá sâu bị từ chối, cũng khác với offset nằm sau entity cuối của một query thực thi thành công.

Đối với empty state:

| Trạng thái | Metadata nên biểu đạt |
| --- | --- |
| Toàn bộ filter không có kết quả | Tổng bằng không nếu đã biết điều đó |
| Trang quá xa nhưng tập còn dữ liệu | Nội dung rỗng cùng tổng đã xác định hoặc chính sách ngoài phạm vi |
| Chưa yêu cầu tổng | Không công bố một số giả làm total |
| Không thực hiện được truy vấn | Đường lỗi hoặc trạng thái suy giảm đã được thiết kế |

## 15. Xác nhận khả năng theo module và loại query

Không chỉ kiểm tra tên store; cần kiểm tra tổ hợp thực tế:

| Tổ hợp | Điều cần xác nhận |
| --- | --- |
| JPA derived Page/Slice | Predicate, projection, count, sort và paging được giải quyết đúng |
| JPQL/SQL native khai báo | Cách áp dụng sort/limit, query đếm và mapping |
| JPA scrolling | Bộ phiên bản, loại query, loại ScrollPosition và khóa sort được hỗ trợ |
| Kho tài liệu hoặc công cụ tìm kiếm | API tiếp tục, giới hạn truy cập sâu, semantics count và sort |
| JDBC so với R2DBC | Phân biệt đồng bộ và reactive, không suy hỗ trợ wrapper từ việc cùng dùng SQL |
| Repository reactive | Chữ ký publisher được hỗ trợ; `Mono<Page<T>>` không tự có chỉ vì Commons định nghĩa Page |
| Fragment tùy biến | Implementation thực sự đáp ứng metadata và ngân sách truy cập đã hứa |

Commons cung cấp nền tảng chung. Nó không tự chuyển SQL thành một query tài liệu, biến publisher thành một tổng số hoặc tạo cursor cho mọi nguồn truy vấn.

Một adapter có thể giúp tầng ứng dụng giữ hình dạng DTO nhất quán, nhưng không được làm mất các giới hạn có ý nghĩa của backend. Khi không thể cung cấp một khả năng ở chi phí phù hợp, cần điều chỉnh hợp đồng trước khi tạo một lớp giả lập tốn kém.

## 16. Đo lường và kiểm thử hợp đồng cùng chi phí

### 16.1. Những chỉ số hữu ích

Theo use case và store có thể quan sát:

- Thời gian lấy nội dung và thời gian count nếu có.
- Số lượt truy cập dữ liệu trong toàn bộ quá trình tạo phản hồi.
- Kích thước nội dung, số trường và lượng dữ liệu trả về.
- Chi phí ở các vùng offset khác nhau, không chỉ trang đầu.
- Hành vi sort và chỉ mục theo query plan hoặc cơ chế chẩn đoán backend.
- Số lần tải quan hệ phát sinh ở mapper/serialization nếu có.

Không cần đưa các chi tiết này vào flow sản phẩm nếu chúng không giúp người dùng quyết định. Chúng cần có ở nơi nhóm phát triển và vận hành đánh giá được nghĩa vụ mà hợp đồng đã tạo ra.

### 16.2. Kiểm thử kết quả

Các trường hợp nên phân biệt:

| Trường hợp | Bằng chứng cần có |
| --- | --- |
| Trang đầu, giữa, cuối | Nội dung và metadata đúng |
| Tổng chia hết cho size | `hasNext` không bị suy sai từ kích thước nội dung |
| Không có kết quả và trang vượt cuối | Không làm mất sự khác nhau của total |
| Nhiều entity cùng khóa chính | Thứ tự có khóa phụ đúng |
| Bộ lọc tenant/trạng thái | Nội dung và count đếm cùng tập |
| DTO projection | Có đúng dữ liệu cần dùng và mapping phù hợp |
| Thay đổi size/sort/filter | Vị trí mới tuân chính sách API |

### 16.3. Kiểm thử nghĩa vụ truy cập dữ liệu

Nếu hợp đồng feed không cần tổng, cần chứng minh đường đó không gọi một count chỉ để bỏ kết quả. Nếu hợp đồng quản trị có tổng, kiểm tra count tương đương predicate nội dung.

Khi muốn quan sát đường count, fixture phải đủ lớn để implementation không luôn suy ra tổng từ một trang đầu ngắn. Không viết assertion rằng mọi Page luôn có đúng hai truy vấn, vì một số nhánh hợp lệ có thể tránh count.

Cũng không chỉ assert số truy vấn tại repository rồi bỏ qua mapper tạo response. Một phép đo có ý nghĩa cần bao phủ đường sử dụng đã cam kết, đồng thời tách các truy vấn chuẩn bị fixture khỏi công việc đang đánh giá.

Nếu đánh giá offset sâu hoặc keyset, dùng dữ liệu và kế hoạch thực thi phù hợp backend mục tiêu. Một test vài hàng trong store thay thế không chứng minh ngân sách hiệu năng trên dữ liệu thực tế.

## 17. Bài tập thiết kế

### Bài 1: Một abstraction cho ba màn hình

Một hàm `search(...)` luôn trả `Page<OrderSummary>` được dùng cho bảng quản trị, feed xem tiếp và widget năm đơn mới nhất.

**Phân tích:** bảng có thể cần Page, feed có thể chỉ cần Slice/Window, widget có thể chỉ cần danh sách giới hạn. Cần xác định từng nghĩa vụ trước khi thống nhất abstraction. Một kiểu trả về chung không có nghĩa các caller có cùng nhu cầu count.

### Bài 2: Tổng bằng không hay chưa tính?

Feed có hai phần tử và `hasNext = true`, nhưng DTO mặc định `totalElements = 0` vì chưa chạy count.

**Phân tích:** metadata mâu thuẫn. Hợp đồng nên bỏ trường tổng hoặc biểu đạt rõ tổng không được cung cấp, thay vì dùng số không với nghĩa khác.

### Bài 3: Size nhỏ nhưng endpoint chậm

Mỗi trang chỉ có hai mươi đơn. Quan sát cho thấy count join tốn phần lớn thời gian, mapper còn đọc thêm quan hệ cho từng đơn.

**Phân tích:** tăng tốc nội dung query chưa đủ. Cần xem caller có thật sự cần total, count có đúng đơn vị và mapper có đang tạo truy vấn bổ sung. Chọn projection/fetch strategy phải đi cùng việc giữ đúng semantics trang.

### Bài 4: Cursor có thay được mọi page index?

Một sản phẩm đổi sang cursor nhưng vẫn hứa người dùng nhảy thẳng tới trang số bất kỳ mà không có mốc trước đó.

**Phân tích:** cần thiết kế một khả năng khác để đáp ứng lời hứa đó hoặc điều chỉnh flow điều hướng. Cursor tiếp tục không tự cung cấp địa chỉ của mọi trang số.

### Bài 5: Count lỗi nhưng nội dung đã có

Ứng dụng muốn vẫn trả dữ liệu khi count lỗi.

**Phân tích:** đây là một quyết định hợp đồng suy giảm chức năng. Cần phân biệt tổng không cung cấp được với tổng bằng không, và quyết định caller xử lý ra sao. Không trả một Page thành công với total giả chỉ để giữ cùng kiểu dữ liệu.

## 18. Các điểm cần nhớ

- Hợp đồng phân trang bắt đầu từ nhu cầu tổng số, điều hướng, dữ liệu trả về và mức nhất quán của caller.
- Page giao thêm nghĩa vụ metadata tổng; bỏ trường tổng ở response không tự loại bỏ chi phí đã phát sinh.
- Slice, Window và danh sách giới hạn có thể phù hợp hơn cho những nhu cầu khác, nhưng phải thuộc khả năng thực tế của module/store.
- Offset, count, sort, mapping và tải quan hệ là các nhóm chi phí riêng cần được quan sát trong toàn bộ use case.
- Metadata phải phân biệt tổng bằng không, tổng chưa cung cấp, trang vượt phạm vi và lỗi truy vấn.
- Abstraction tốt giúp nhóm phát triển nhìn thấy những nghĩa vụ đã chọn, giữ API rõ ràng và không giả lập một khả năng tốn kém phía sau một chữ ký tưởng như đơn giản.
