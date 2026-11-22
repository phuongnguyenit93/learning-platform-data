# Phi chuẩn hóa (denormalization), dữ liệu lặp và chính sách đồng bộ

## 1. Vì sao cần phi chuẩn hóa trong MongoDB?

Trong chương **Thiết kế document** của **Spring Data MongoDB**, một quyết định quan trọng là đặt dữ liệu vào một document, giữ dữ liệu ở collection riêng và tham chiếu bằng ID, hay **sao chép có chủ đích** một phần thông tin sang nhiều document để phục vụ thao tác đọc.

**Phi chuẩn hóa (denormalization)** là tổ chức dữ liệu theo nhu cầu truy cập, có thể chấp nhận lưu lặp một thông tin thay vì chỉ giữ một bản và truy vấn liên kết mỗi lần đọc. Chẳng hạn, trang đơn hàng cần hiển thị tên sản phẩm và đơn giá tại lúc mua; trang danh mục lại cần hiển thị nhanh tên và giá *hiện hành* của sản phẩm. Hai nhu cầu này có vẻ giống nhau nhưng đòi hỏi **hai chính sách đồng bộ khác nhau**.

Phi chuẩn hóa thường giúp:

- Lấy đủ thông tin cho một màn hình hoặc một thao tác chỉ bằng một truy vấn hoặc ít lần truy cập hơn.
- Giảm số lần ứng dụng phải truy vấn thêm collection để bổ sung thông tin.
- Đặt những dữ liệu thường được đọc, cập nhật cùng nhau trong một document khi kích thước và quan hệ phù hợp.
- Xây dựng một *read model* để tối ưu truy vấn tìm kiếm, phân trang, báo cáo hoặc hiển thị.

Đổi lại, hệ thống phải xử lý **khuếch đại ghi** (một thay đổi ở nguồn kéo theo nhiều bản sao), **dữ liệu cũ** (*stale data*), lỗi đồng bộ và quy tắc xác định bản nào có thẩm quyền.

> Quy tắc nền tảng: trước khi sao chép một trường, hãy xác định bản sao đó biểu diễn **sự thật tại một thời điểm trong quá khứ** hay **trạng thái mới nhất phải được cập nhật**. Hai trường hợp này không được áp dụng cùng một chính sách.

## 2. Ba mô hình lưu dữ liệu cần phân biệt

### 2.1. Nhúng dữ liệu trong cùng document (*embedding*)

Ví dụ một đơn hàng chứa danh sách dòng hàng và địa chỉ giao hàng:

~~~json
{
  "_id": "o-1001",
  "customerId": "c-12",
  "placedAt": "2026-11-20T08:00:00Z",
  "shippingAddressAtOrder": {
    "city": "Hà Nội",
    "street": "12 Phố Ví Dụ"
  },
  "items": [
    {
      "productId": "p-101",
      "titleAtOrder": "Bình nước 500 ml",
      "unitPriceVnd": 129000,
      "quantity": 2
    }
  ],
  "totalVnd": 258000
}
~~~

Một lần đọc đơn hàng đã có đủ thông tin để lập biên nhận. Danh sách mặt hàng thường có kích thước **hữu hạn theo một đơn hàng**, nên đây là một ứng viên hợp lý để nhúng. Tuy vậy, không nên nhúng một mảng tăng vô hạn, ví dụ *toàn bộ* đơn hàng của một khách vào document khách hàng: document MongoDB có giới hạn kích thước BSON **16 MiB**, và việc cập nhật mảng quá lớn làm tăng độ phức tạp, tải ghi và rủi ro xung đột.

Nhúng không đồng nghĩa với việc cần đồng bộ mọi trường. `titleAtOrder` và `unitPriceVnd` là **ảnh chụp lịch sử**; cập nhật tên hoặc giá hiện tại của sản phẩm không được viết lại đơn hàng cũ.

### 2.2. Tham chiếu giữa các document (*referencing*)

Với quan hệ nhiều phần tử, tăng trưởng độc lập, có thể lưu ID thay vì nhúng toàn bộ:

~~~json
{
  "_id": "review-900",
  "productId": "p-101",
  "authorId": "u-42",
  "rating": 5,
  "comment": "Giữ nhiệt tốt"
}
~~~

Sản phẩm không cần chứa mọi review. Khi cần tổng hợp đánh giá, ứng dụng có thể truy vấn collection review theo `productId`, dùng aggregation hoặc cân nhắc lưu một giá trị tổng hợp ở document sản phẩm.

Tham chiếu thủ công bằng ID là lựa chọn phổ biến. MongoDB cũng có `$lookup` trong aggregation để kết hợp dữ liệu từ collection khác. Vì vậy, **không cần sao chép dữ liệu chỉ vì nghĩ rằng MongoDB không thể kết hợp collection**; hãy đánh giá chi phí truy vấn và tần suất đọc thực tế.

### 2.3. Nhân bản có kiểm soát sang read model

Giả sử collection nguồn lưu sản phẩm:

~~~json
{
  "_id": "p-101",
  "title": "Bình nước 500 ml",
  "priceVnd": 129000,
  "categoryId": "bottles",
  "version": 8
}
~~~

Để phục vụ màn hình tìm kiếm, ứng dụng có thể duy trì collection `product_cards`:

~~~json
{
  "_id": "p-101",
  "title": "Bình nước 500 ml",
  "priceVnd": 129000,
  "sourceVersion": 8
}
~~~

Bản thứ hai là **projection**: bản sao có thể tái tạo từ sản phẩm nguồn. Khi sản phẩm đổi tên hoặc giá, projection cần cập nhật theo chính sách đã công bố, ví dụ độ trễ được chấp nhận tối đa 60 giây. Đây là **dữ liệu dẫn xuất đang sống**, khác với ảnh chụp lịch sử trong đơn hàng.

## 3. Khi nào nên nhúng, tham chiếu hoặc sao chép?

| Đặc điểm nghiệp vụ | Hướng thiết kế thường phù hợp | Câu hỏi phải trả lời |
|---|---|---|
Nhóm trường cùng vòng đời, thường đọc cùng nhau, số lượng nhỏ/có giới hạn | Nhúng trong document | Document có tăng kích thước vượt kiểm soát không? |
Quan hệ một-nhiều rất lớn hoặc hai thực thể cập nhật độc lập | Tham chiếu ID | Cần index/truy vấn bổ sung nào để đọc hiệu quả? |
Thông tin phải giữ đúng tại thời điểm phát sinh giao dịch | Sao chép thành snapshot lịch sử | Mốc thời gian chốt bản sao và quy định sửa sai là gì? |
Thông tin nguồn đổi thường xuyên nhưng màn hình cần đọc nhanh | Projection/bản sao đồng bộ | Cho phép trễ bao lâu và xử lý sự kiện sai thứ tự ra sao? |
Điều kiện đọc phức tạp nhưng số truy vấn ít, dữ liệu không quá lớn | Tham chiếu + aggregation/`$lookup` | Có thật sự cần thêm bản sao để tối ưu không? |
Trường quyết định thanh toán, hạn mức, số lượng tồn | Đọc/ghi dữ liệu có thẩm quyền tại điểm quyết định | Nếu bản sao chậm, kết quả nghiệp vụ có sai không? |

Không có quy tắc “nhúng luôn nhanh hơn” hay “tham chiếu luôn tốt hơn”. Cần xét **hình dạng truy vấn**, kích thước dữ liệu, số lần ghi, độ thay đổi, tính nhất quán và khả năng khôi phục sau lỗi.

Một cách định lượng sơ bộ:

- **Lợi ích đọc**: số lần đọc và lượng dữ liệu truyền đi giảm được bao nhiêu khi có bản sao?
- **Chi phí ghi**: khi một sản phẩm thay đổi, có bao nhiêu bản sao phải cập nhật? Một sản phẩm xuất hiện trong 10 hay 100.000 document?
- **Độ trễ**: ứng dụng chịu được bản sao cũ trong vài giây, vài phút hay không được cũ?
- **Khả năng sửa sai**: có thể dựng lại toàn bộ projection từ nguồn không? Có công cụ phát hiện bản sao thiếu hoặc sai không?

Đối với thiết kế MongoDB, **ranh giới nguyên tử của một document** cũng rất quan trọng: một thao tác cập nhật một document có tính nguyên tử tại document đó. Nếu thông tin phải thay đổi cùng nhau theo một bất biến nghiệp vụ, việc giữ chúng trong cùng document thường đơn giản hơn việc đồng bộ nhiều document.

## 4. Xác định “nguồn chân lý” và ý nghĩa từng bản sao

Trước khi viết mã đồng bộ, nên lập hợp đồng dữ liệu cho mỗi nhóm trường:

| Trường dữ liệu | Nguồn có thẩm quyền | Ý nghĩa bản sao | Chính sách |
|---|---|---|---|
`orders.items[].titleAtOrder` | Sản phẩm tại lúc chốt đơn | Tên xuất hiện trên đơn đã phát sinh | Chốt một lần; không chạy cập nhật theo tên mới |
`orders.items[].unitPriceVnd` | Giá được xác nhận khi mua | Giá lịch sử để tính tổng đơn | Chốt một lần; không đồng bộ theo giá niêm yết mới |
`product_cards.title` | `products.title` | Tên sản phẩm hiện tại cho màn hình danh mục | Đồng bộ sau thay đổi, có đo độ trễ |
`product_cards.priceVnd` | `products.priceVnd` | Giá tham khảo trên màn hình | Đồng bộ gần thời gian thực; xác minh lại khi thanh toán |
`products.availableStock` | Trạng thái tồn kho/quy trình giữ hàng có thẩm quyền | Số lượng có thể đặt | Quyết định giữ hàng phải dùng thao tác an toàn tại nguồn; bản hiển thị có thể là gần đúng |

Hai lưu ý quan trọng:

1. **Sao chép giá và tồn kho để hiển thị không có nghĩa là được dùng bản sao làm quyết định cuối cùng.** Luồng tạo đơn phải kiểm tra hoặc giữ hàng ở nguồn có thẩm quyền theo quy tắc chống tranh chấp, đồng thời chốt giá nghiệp vụ phù hợp.
2. **“Lịch sử không đồng bộ” không có nghĩa dữ liệu được lưu vô hạn hoặc bất biến trong mọi trường hợp.** Yêu cầu sửa đơn, bảo vệ dữ liệu cá nhân, xóa theo chính sách lưu trữ hoặc quy định pháp lý có thể cần điều chỉnh theo một quy trình kiểm soát riêng.

Nếu không xác định rõ nguồn chân lý, một thay đổi xuất phát từ read model có thể bị đồng bộ ngược, gây vòng cập nhật và kết quả bất định.

## 5. Các chính sách đồng bộ dữ liệu lặp

### 5.1. Không đồng bộ lại: snapshot có chủ đích

Khi đặt đơn, hệ thống đọc tên và giá được chấp nhận tại thời điểm chốt giao dịch rồi lưu vào đơn hàng. Sau đó:

- Sản phẩm đổi tên: đơn cũ vẫn giữ tên tại lúc mua.
- Giá niêm yết đổi: đơn cũ vẫn giữ giá đã xác nhận.
- Sản phẩm bị ẩn khỏi danh mục: hóa đơn/đơn hàng vẫn có thông tin lịch sử cần thiết, theo chính sách lưu trữ.

Snapshot giúp lịch sử không phụ thuộc vào việc collection sản phẩm có còn bản ghi hay không. Tuy nhiên, chốt snapshot phải diễn ra trong quy trình đặt hàng đúng đắn, cùng với các kiểm tra giá, kho và phiên bản dữ liệu cần thiết; **không** thể giả định rằng nhiều lần đọc/ghi rời rạc tự có tính nhất quán giao dịch.

### 5.2. Cập nhật trong cùng document

Nếu dữ liệu nguồn và dữ liệu cần cập nhật cùng nằm trong **một document**, có thể cập nhật bằng một thao tác MongoDB, ví dụ `$set` nhiều trường trong một lệnh. Đây là lựa chọn đơn giản khi tất cả bản sao có ranh giới nhỏ và cùng vòng đời.

Nhược điểm là document có thể phình lớn, và dữ liệu của nhiều thực thể cập nhật độc lập sẽ bị buộc chung vào một điểm tranh chấp. Đừng nhúng danh sách vô hạn chỉ để tận dụng tính nguyên tử.

### 5.3. Cập nhật nhiều document trong transaction

Khi một bất biến thực sự cần thay đổi đồng thời ở nhiều document, MongoDB hỗ trợ transaction nhiều document trên topology được hỗ trợ, như replica set hoặc sharded cluster. Trong ứng dụng Spring Data MongoDB dạng đồng bộ, có thể cấu hình `MongoTransactionManager` và sử dụng transaction qua `@Transactional` nếu mọi thao tác cần thiết tham gia đúng session.

Điểm cần cân nhắc:

- Transaction tăng chi phí tài nguyên, độ trễ và khả năng gặp xung đột so với một thao tác một document.
- Cập nhật hàng nghìn bản sao chỉ vì một sản phẩm đổi tên thường không phù hợp với transaction đồng bộ trong đường xử lý yêu cầu của người dùng.
- Cần xử lý retry cho lỗi transaction có thể thử lại và bảo đảm các tác dụng bên ngoài (gửi email, phát sự kiện) không bị lặp ngoài ý muốn.
- Gọi driver trực tiếp ngoài session đang được quản lý có thể khiến một thao tác nằm ngoài transaction của Spring Data.

Chỉ áp dụng transaction khi yêu cầu nhất quán thực sự đáng chi phí; **độ nhất quán không cần thiết cho một read model có thể tạo ra nút nghẽn ghi**.

### 5.4. Đồng bộ bất đồng bộ qua sự kiện

Một chiến lược phổ biến là **nguồn ghi trước, read model cập nhật sau**:

~~~mermaid
flowchart LR
    U["Yêu cầu đổi sản phẩm"] --> S["Ghi products: version 9"]
    S --> E["Sự kiện thay đổi đã được ghi nhận bền vững"]
    E --> W["Worker xử lý sự kiện"]
    W --> P["Cập nhật product_cards nếu version mới hơn"]
    P --> R["Màn hình đọc projection"]
    W --> C["Checkpoint và theo dõi độ trễ"]
    F["Đối soát định kỳ"] --> P
~~~

Các cách lấy sự kiện gồm:

- **Transactional outbox**: ghi thay đổi nguồn và một bản ghi sự kiện vào database trong cùng transaction phù hợp; một tiến trình riêng phát/đọc sự kiện sau khi commit. Nếu outbox nằm ở document khác, phải bảo đảm transaction nhiều document thật sự hoạt động.
- **MongoDB change streams**: theo dõi thay đổi đã commit trên collection/database để kích hoạt cập nhật projection. Change streams yêu cầu môi trường MongoDB hỗ trợ (ví dụ replica set hoặc sharded cluster), quản lý **resume token**, theo dõi gián đoạn và lưu checkpoint bền vững. Không nên dựa vào `fullDocument` đọc bổ sung để mặc định tái dựng chính xác mọi trạng thái trung gian khi nguồn đổi liên tiếp.
- **Hàng đợi sự kiện bền vững**: ứng dụng ghi/đẩy sự kiện bằng một cơ chế bảo đảm không bị “ghi nguồn thành công nhưng quên phát sự kiện”. Chỉ gọi broker sau lệnh `save` mà không có cơ chế khôi phục có thể tạo mất đồng bộ.

Worker tiêu thụ sự kiện phải chịu được **xử lý lặp và sự kiện đến sai thứ tự**. Thực tế cần cơ chế retry, dead-letter/quarantine cho lỗi kéo dài, cảnh báo độ trễ và khả năng phát lại. Với các thao tác bị xóa, cần event hoặc tombstone riêng; không thể giả định có đủ thông tin của bản ghi bị xóa để tự tái tạo projection.

### 5.5. Làm mới khi đọc và đối soát định kỳ

**Lazy refresh** kiểm tra phiên bản hoặc hạn sử dụng khi đọc projection; nếu cũ thì lấy lại từ nguồn, cập nhật cache/projection rồi trả kết quả. Cách này giảm ghi liên tục nhưng làm chậm một số request và cần giới hạn tải khi nhiều request cùng làm mới.

**Đối soát định kỳ** so sánh nguồn và bản sao để tìm phần tử thiếu, sai phiên bản hoặc bị xóa không đúng. Có thể kết hợp quét theo batch, watermark hoặc cập nhật gần nhất. Đối soát là cơ chế phục hồi quan trọng ngay cả khi đã có change streams hoặc event queue.

| Chiến lược | Độ mới dữ liệu | Chi phí chính | Trường hợp hợp lý |
|---|---|---|---|
Snapshot, không đồng bộ | Cố định tại thời điểm chốt | Lưu trữ lịch sử | Dòng hàng, đơn giá, điều khoản tại lúc ký/mua |
Cùng document | Nhất quán sau thao tác cập nhật đơn lẻ | Document lớn và tranh chấp ghi | Nhóm dữ liệu nhỏ, cùng vòng đời |
Transaction nhiều document | Có thể nhất quán tại commit khi cấu hình đúng | Transaction, retry, tài nguyên | Bất biến nghiệp vụ bắt buộc thay đổi cùng nhau |
Sự kiện bất đồng bộ | Nhất quán cuối cùng (*eventual consistency*) | Độ trễ, event pipeline, phục hồi | Search card, read model, thống kê gần thời gian thực |
Làm mới khi đọc | Tùy TTL/version và yêu cầu đọc | Độ trễ và tải nguồn vào lúc đọc | Dữ liệu ít đọc hoặc cập nhật không thường xuyên |
Đối soát định kỳ | Phụ thuộc chu kỳ quét | Tải kiểm tra và sửa dữ liệu | Lớp an toàn bổ sung cho mọi projection quan trọng |

## 6. Mẫu triển khai projection với Spring Data MongoDB

Ví dụ sau minh họa **projection được đồng bộ bất đồng bộ**. `products` là nguồn có thẩm quyền; `product_cards` là bản sao tối ưu đọc. Một sự kiện `ProductChanged` mang theo trạng thái cần trình bày cùng **phiên bản nguồn tăng đơn điệu**.

### 6.1. Ghi phiên bản tại nguồn

Spring Data MongoDB hỗ trợ optimistic locking qua `@Version` trên entity, giúp phát hiện việc ghi đè bản cập nhật đã bị thay đổi đồng thời khi dùng các đường ghi hỗ trợ version:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public class Product {
    @Id
    public String id;
    @Version
    public Long version;
    public String title;
    public long priceVnd;
}
~~~

Đoạn code dùng trường public để tập trung vào cơ chế mapping; trong ứng dụng thực tế nên đóng gói entity và kiểm soát thao tác ghi. **Không** dùng `updatedAt` có độ phân giải không đủ hoặc đồng hồ của nhiều máy làm thứ tự tuyệt đối nếu cần chặn sự kiện cũ. Phiên bản phải tăng theo cùng một thực thể khi thay đổi được chấp nhận. Với `@Version`, cần kiểm tra cách lưu, cập nhật và thao tác custom để bảo đảm không có đường ghi nào âm thầm bỏ qua version.

### 6.2. Mô hình bản sao và sự kiện

~~~java
// ProductCard.java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "product_cards")
public record ProductCard(
        @Id String id,
        String title,
        long priceVnd,
        long sourceVersion) {}
~~~

~~~java
// ProductChanged.java
public record ProductChanged(
        String productId,
        String title,
        long priceVnd,
        long sourceVersion) {}
~~~

Mỗi card dùng `_id` cùng ID sản phẩm để bảo đảm duy nhất. Sự kiện phải mô tả **trạng thái nguồn đã được commit**, không phát từ dữ liệu chưa commit. Với các thao tác thay đổi nhiều trường, sự kiện cần chứa trạng thái đủ để tái tạo projection hoặc chứa một khóa/phiên bản để tải lại đúng trạng thái đã commit theo chính sách phù hợp.

### 6.3. Chống ghi đè bởi sự kiện cũ

Worker nhận sự kiện có thể cập nhật card nếu `sourceVersion` thấp hơn phiên bản sự kiện. Nếu card chưa có, worker tạo bản mới; nếu hai worker tạo đồng thời, khóa duy nhất `_id` sẽ chặn tạo trùng và worker thử cập nhật có điều kiện lần nữa.

~~~java
// ProductCardProjector.java
import com.mongodb.client.result.UpdateResult;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Component;

@Component
public class ProductCardProjector {
    private final MongoTemplate mongo;

    public ProductCardProjector(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public void apply(ProductChanged event) {
        Query onlyNewer = new Query(
                Criteria.where("_id").is(event.productId())
                        .and("sourceVersion").lt(event.sourceVersion()));

        Update changes = new Update()
                .set("title", event.title())
                .set("priceVnd", event.priceVnd())
                .set("sourceVersion", event.sourceVersion());

        UpdateResult updated = mongo.updateFirst(
                onlyNewer, changes, ProductCard.class);
        if (updated.getMatchedCount() == 1) {
            return;
        }

        // Có thể card chưa tồn tại, hoặc sự kiện đã cũ / đã xử lý.
        try {
            mongo.insert(new ProductCard(
                    event.productId(),
                    event.title(),
                    event.priceVnd(),
                    event.sourceVersion()));
        } catch (DuplicateKeyException duplicate) {
            // Card đã có (có thể do worker khác vừa tạo).
            // Điều kiện version bảo vệ khỏi ghi đè bằng sự kiện cũ.
            mongo.updateFirst(onlyNewer, changes, ProductCard.class);
        }
    }
}
~~~

Ý nghĩa với các sự kiện đến theo thứ tự **v9 → v8 → v9 (lặp) → v10**:

1. v9 tạo card nếu chưa có hoặc cập nhật một card có version nhỏ hơn 9.
2. v8 bị bỏ qua vì nguồn version 8 không mới hơn 9.
3. v9 lặp lại không thay đổi nội dung card.
4. v10 cập nhật card lên version 10.

Đây là cơ chế **idempotent theo trạng thái cuối** cho projection dạng thay thế giá trị. Nó **không** phù hợp nếu event mang ý nghĩa “cộng thêm 1” và mỗi sự kiện phải được áp dụng chính xác một lần. Với sự kiện delta như tăng bộ đếm, cần thiết kế khóa idempotency/event ID, thứ tự áp dụng hoặc cách tính lại từ nguồn.

Ví dụ chưa bao gồm phần tiêu thụ broker/change stream, checkpoint, retry, xóa sản phẩm và phát sự kiện. Những phần đó cần triển khai riêng theo hợp đồng dữ liệu:

- Chỉ checkpoint sau khi cập nhật projection bền vững hoặc đã xác nhận sự kiện không cần áp dụng.
- Nếu ghi thất bại vì lỗi kết nối, retry; không coi mọi lỗi là lỗi duplicate hợp lệ.
- Khi xóa, cân nhắc ghi **tombstone có version** để sự kiện cập nhật cũ không tạo lại sản phẩm đã xóa; chỉ xóa tombstone khi an toàn theo thời hạn lưu sự kiện.
- Với thao tác đổi loại danh mục, đồng bộ cả việc thêm mới và loại bỏ bản sao khỏi danh mục cũ.

### 6.4. Đọc projection

~~~java
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductCardRepository
        extends MongoRepository<ProductCard, String> {
}
~~~

~~~java
// Ví dụ trong lớp service có ProductCardRepository cards:
Optional<ProductCard> card = cards.findById("p-101");
~~~

Với yêu cầu phải thấy **ngay** giá vừa cập nhật, luồng đọc này có thể không phù hợp vì projection xử lý bất đồng bộ. Có thể đọc nguồn trực tiếp hoặc dùng một chính sách kiểm tra phiên bản nhất quán phù hợp với thao tác. Cần xác định trải nghiệm sau khi ghi của cùng người dùng (*read-your-writes*) thay vì mặc định mọi người đều chấp nhận độ trễ.

## 7. Những tình huống khó khi đồng bộ

### 7.1. Sự kiện sai thứ tự, lặp và cập nhật đồng thời

Một event pipeline có thể giao lại sự kiện sau retry, xử lý song song hoặc đến sai thứ tự. **Mỗi bản sao cần dấu phiên bản** cho nguồn đang chi phối nó. Nếu một document tổng hợp từ nhiều nguồn (sản phẩm, người bán, kho), một `sourceVersion` duy nhất thường không đủ: cần phiên bản riêng cho từng nguồn hoặc một quy trình tổng hợp xác định rõ thứ tự.

### 7.2. Xóa và tái tạo

Xóa bản sao khi nhận một sự kiện xóa cũ có thể vô tình xóa dữ liệu vừa được tạo lại. Cần phân biệt **ID mới** và **tái sử dụng ID**, đồng thời đặt quy tắc version/tombstone. Một số ứng dụng dùng trạng thái `deletedAt` hoặc `isDeleted` trên nguồn và đẩy projection theo cùng luồng version để kiểm soát vòng đời.

### 7.3. Mất sự kiện và phục hồi sau gián đoạn

Ngay cả khi mỗi lần xử lý có kiểm tra version, **một sự kiện bị mất** vẫn làm bản sao mãi cũ nếu không có cơ chế khác. Cần:

- Lưu checkpoint/resume token bền vững phù hợp.
- Phát hiện consumer bị ngắt, tụt sau nguồn hoặc không thể tiếp tục bằng token cũ.
- Chạy đối soát và tái dựng projection từ dữ liệu có thẩm quyền.
- Kiểm soát tốc độ backfill để tránh gây quá tải collection nguồn.

### 7.4. Dữ liệu nhạy cảm và thay đổi cấu trúc

Mỗi bản sao mới làm tăng nơi phải quản lý quyền truy cập, mã hóa, thời hạn lưu và xóa dữ liệu. Tránh sao chép email, địa chỉ, số điện thoại chỉ để tiết kiệm một truy vấn nếu không có nhu cầu rõ ràng. Khi đổi schema, cần định nghĩa `schemaVersion` hoặc chiến lược migration/backfill để consumer cũ và mới không diễn giải sự kiện theo những cách mâu thuẫn.

### 7.5. Index và khuếch đại ghi

Một document nguồn có thể sinh nhiều bản sao và mỗi bản sao có nhiều index. Thay đổi một trường có index có thể làm tăng số thao tác ghi cần xử lý. Khi cân nhắc phi chuẩn hóa, kiểm tra:

- Số lượng bản sao trên mỗi thay đổi nguồn; độ lớn và tốc độ tăng của document.
- Tổng số index, chi phí cập nhật index và dung lượng lưu.
- Khả năng phân phối truy vấn đọc/ghi, tính chọn lọc của index và chi phí aggregation.
- Khả năng hệ thống duy trì SLA đồng bộ trong giờ cao điểm.

## 8. Đo lường và kiểm thử chính sách đồng bộ

Một thiết kế hữu ích phải có **tiêu chí kiểm chứng được**. Ví dụ chính sách cho `product_cards`:

| Thuộc tính | Hợp đồng ví dụ |
|---|---|
Nguồn có thẩm quyền | `products` |
Phạm vi bản sao | `id`, `title`, `priceVnd` và `sourceVersion` |
Độ trễ mục tiêu | 95% sự kiện được phản ánh dưới 30 giây; mọi sự kiện dưới 2 phút trong vận hành bình thường |
Tính đúng đắn | Không để event phiên bản nhỏ hơn ghi đè phiên bản lớn hơn |
Khôi phục | Retry lỗi tạm thời; cảnh báo sự kiện lỗi kéo dài; đối soát và backfill được |
Giới hạn sử dụng | Chỉ dùng để hiển thị; giá và tồn kho được xác minh lại tại thời điểm chốt đơn |

Các ngưỡng 30 giây và 2 phút **chỉ là ví dụ thiết kế**. Phải chọn theo yêu cầu thực và khả năng hạ tầng.

Với Spring Data MongoDB, có thể viết integration test bằng MongoDB thực trong Testcontainers để kiểm tra dữ liệu BSON và hành vi ghi; nếu kiểm thử change streams/transaction, cần cấu hình MongoDB với topology hỗ trợ. Các kịch bản tối thiểu:

1. Nhận sự kiện v5 hai lần → card có version 5 và không bị sai dữ liệu.
2. Nhận v7 rồi v6 → card giữ version 7.
3. Hai worker đồng thời nhận v8, v9 khi card chưa có → cuối cùng phải là v9.
4. Consumer dừng, nguồn đổi liên tục, consumer chạy lại → có thể bắt kịp nguồn hoặc phục hồi bằng backfill.
5. Sản phẩm bị xóa/ẩn hoặc chuyển danh mục → projection không còn hiển thị dữ liệu lỗi thời.
6. Đơn hàng đã tạo vẫn giữ tên và giá tại thời điểm chốt, dù sản phẩm nguồn đổi.

Ngoài kiểm thử logic, theo dõi **projection lag**, số event đang chờ, tỷ lệ retry, số lỗi không xử lý được, số card thiếu, sai phiên bản và thời lượng backfill. Định kỳ so sánh dữ liệu nguồn với projection theo batch để phát hiện lỗi mà hệ thống sự kiện không tự phát hiện.

## 9. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
Đồng bộ lại giá vào mọi đơn hàng lịch sử | Sai chứng từ, sai số tiền đã chốt | Phân biệt snapshot lịch sử với giá hiện hành |
Nhúng mảng vô hạn vì muốn đọc một document | Document phình lớn, chạm giới hạn BSON, khó cập nhật | Tham chiếu và truy vấn các phần tử ở collection riêng |
Ghi nguồn rồi phát event mà không bảo đảm bền vững | Nguồn đổi nhưng projection không biết | Outbox/CDC đáng tin cậy và đối soát |
Xử lý event không xét thứ tự/version | Event cũ ghi đè dữ liệu mới | Dùng version tăng đơn điệu và cập nhật có điều kiện |
Xem read model là nơi quyết định tồn kho/thanh toán | Đọc dữ liệu chậm, gây bán quá hoặc sai giá | Xác nhận tại nguồn trong thao tác nghiệp vụ |
Chỉ có event consumer, không có backfill | Dữ liệu sai tồn tại mãi sau khi mất event | Thiết kế checkpoint, đối soát và tái dựng |
Sao chép mọi trường “để tiện” | Tăng rủi ro bảo mật, chi phí index và đồng bộ | Chỉ nhân bản trường có nhu cầu đọc và hợp đồng rõ |
Tự động dùng transaction cho mọi projection | Độ trễ ghi, tranh chấp, giảm khả năng mở rộng | Chọn mức nhất quán đúng nhu cầu, ưu tiên eventual consistency khi phù hợp |

## 10. Bài tập vận dụng

**Bài 1 – Thiết kế đơn hàng.** Với dữ liệu khách hàng, sản phẩm, giá hiện tại, giá lúc mua, địa chỉ giao, tồn kho và lịch sử trạng thái, hãy phân loại trường nào nằm ở nguồn, trường nào được chụp vào đơn, trường nào có thể là projection. Giải thích vì sao giá đơn hàng cũ không đổi khi cập nhật giá sản phẩm.

**Bài 2 – Đồng bộ danh mục.** Thiết kế `product_cards` phục vụ liệt kê sản phẩm với độ trễ cho phép 1 phút. Nêu sự kiện, phiên bản, index, checkpoint, cách xử lý event lặp, xóa sản phẩm và cách tái dựng khi consumer ngừng chạy một giờ.

**Bài 3 – Đánh giá chi phí.** Một cửa hàng có 50.000 sản phẩm và mỗi sản phẩm được chèn vào 30 danh sách gợi ý. Tính số bản sao tiềm năng và các thao tác phát sinh khi đổi tên 1.000 sản phẩm. Đề xuất khi nào nên thay bản sao nhúng bằng tham chiếu hoặc read model riêng; không kết luận chỉ từ số lượng mà bỏ qua tần suất cập nhật và thời gian đọc.

**Bài 4 – Kiểm chứng thực nghiệm.** Viết hai cách lấy danh mục: truy vấn nguồn với các phép nối cần thiết và đọc projection. Đo độ trễ đọc, số truy vấn, kích thước dữ liệu, chi phí ghi bổ sung và độ lệch bản sao khi có sự cố. Chọn phương án dựa trên số liệu.

## 11. Ghi nhớ

Phi chuẩn hóa trong **Spring Data MongoDB** là **quyết định thiết kế dữ liệu theo workload và hợp đồng nhất quán**, không đơn thuần là sao chép trường cho nhanh. Nhúng khi dữ liệu có kích thước kiểm soát được và thường được xử lý cùng nhau; tham chiếu khi thực thể tăng trưởng hoặc có vòng đời độc lập; dùng snapshot khi cần bảo toàn lịch sử; dùng read model khi cần tối ưu truy vấn và chấp nhận đồng bộ.

Mỗi bản sao đang sống phải có **nguồn chân lý, điều kiện cập nhật, mức độ trễ chấp nhận được, bảo vệ trước event cũ, cơ chế xử lý xóa và quy trình đối soát**. MongoRepository và MongoTemplate giúp truy cập/mapping dữ liệu, nhưng chính thiết kế nghiệp vụ, index, transaction hoặc event pipeline mới quyết định độ đúng đắn, hiệu năng và khả năng phục hồi của dữ liệu lặp.
