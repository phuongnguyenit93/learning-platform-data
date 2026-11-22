# Đặt tên khóa theo ứng dụng, miền nghiệp vụ và định danh trong Spring Data Redis

Redis lưu dữ liệu theo **key** và **value**. Với một ứng dụng nhỏ, những tên như `user:1` hoặc `cart:5` có vẻ đủ rõ ràng. Nhưng khi nhiều service, môi trường triển khai và nhóm dữ liệu cùng dùng Redis, những key ngắn và thiếu ngữ cảnh sẽ sớm trở thành nguồn gây nhầm lẫn: hai ứng dụng ghi đè dữ liệu của nhau, cùng một tên key bị dùng cho hai kiểu Redis khác nhau, khó biết ai sở hữu dữ liệu và rất khó di trú khi cấu trúc hệ thống thay đổi.

Trong Spring Data Redis, thiết kế tên khóa là một **quy ước kiến trúc**: tên khóa phải nói rõ *ứng dụng nào sở hữu*, *thuộc miền nghiệp vụ nào*, *đại diện loại dữ liệu gì* và *định danh đối tượng cụ thể nào*. Quy ước này cần thống nhất giữa `RedisTemplate`, `StringRedisTemplate`, Spring Cache, Redis Repository và mọi thành phần khác ghi dữ liệu vào cùng Redis.

Bài học xây dựng quy tắc đặt tên từ các thành phần cơ bản, áp dụng bằng Java, phân biệt namespace với khả năng cách ly thật sự và giải thích cách duy trì hợp đồng key khi dùng Redis Cluster hoặc cần thay đổi schema.

## 1. Vì sao tên key là một phần của thiết kế hệ thống?

Redis không có hệ thống bảng và schema theo cách của cơ sở dữ liệu quan hệ. Một Redis string, một Redis hash và một Redis set đều được truy cập thông qua tên key. Redis có thể báo key đang là kiểu dữ liệu nào, nhưng **không tự biết** key đó thuộc service nào hay mang ý nghĩa nghiệp vụ gì.

Ví dụ trong một hệ thống thương mại điện tử:

```text
Service catalog:
    user:42     -> người dùng đã xem một sản phẩm

Service identity:
    user:42     -> thông tin đăng nhập người dùng

Service checkout:
    user:42     -> giỏ hàng hiện tại
```

Nếu ba service trỏ tới cùng Redis DB và ghi cùng tên `user:42`, một bên có thể ghi đè giá trị của bên khác. Kết quả phụ thuộc thứ tự ghi; bên đọc còn có thể gặp lỗi `WRONGTYPE` hoặc lỗi deserialize do value không còn đúng format.

Đặt tên có đủ ngữ cảnh sẽ tránh nhầm lẫn:

```text
shop:prod:catalog:recent-view:u42
shop:prod:identity:profile:u42
shop:prod:checkout:cart:u42
```

Từ khóa, người vận hành có thể nhận ra ba nhóm dữ liệu độc lập, mặc dù chúng cùng liên quan người dùng `u42`. Tên key cũng giúp điều tra sự cố, đặt quy tắc quan sát, chọn pattern ACL phù hợp và lập kế hoạch di trú.

**Nguyên tắc:** Một key nên có một chủ sở hữu và một ý nghĩa nghiệp vụ rõ ràng. Nếu hai ứng dụng cố ý dùng chung key, định dạng dữ liệu, quyền ghi, TTL và quy trình đổi schema phải là một hợp đồng được thống nhất.

## 2. Cấu trúc đề xuất: ứng dụng → môi trường → miền → loại → định danh

Một quy tắc dễ áp dụng cho hệ thống gồm nhiều service là:

```text
<application>:<environment>:<domain>:<entity-or-purpose>:<identity>
```

Ví dụ:

```text
shop:prod:catalog:product:p42
shop:prod:checkout:cart:c817
shop:prod:orders:order:o2026-1201
shop:staging:identity:session:s912
```

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| `application` | Dữ liệu thuộc hệ thống hoặc ứng dụng nào? | `shop`, `billing`, `learning` |
| `environment` | Dữ liệu thuộc môi trường chạy nào? | `dev`, `staging`, `prod` |
| `domain` | Miền nghiệp vụ hoặc bounded context nào sở hữu? | `catalog`, `checkout`, `identity`, `orders` |
| `entity-or-purpose` | Loại thực thể hoặc mục đích lưu trữ là gì? | `product`, `cart`, `session`, `rate-limit` |
| `identity` | Bản ghi/đối tượng cụ thể là cái nào? | `p42`, `c817`, `s912` |

Tên miền nghiệp vụ nên phản ánh **ngôn ngữ nghiệp vụ mà đội phát triển cùng hiểu**, thay vì tên class Java tùy ý. Chẳng hạn `checkout:cart` bền vững hơn `CartRedisServiceImpl`, vì tên class có thể đổi trong quá trình refactor nhưng ngữ nghĩa giỏ hàng vẫn giữ nguyên.

Không có cú pháp namespace bắt buộc từ Redis. Dấu `:` chỉ là một quy ước phổ biến trong tên key, giúp con người và công cụ nhận biết các nhóm. Redis xem toàn bộ chuỗi key là một định danh nhị phân; nó **không tự tạo thư mục hoặc ranh giới database** cho mỗi dấu `:`.

### Khi nào cần thêm bớt thành phần?

Cấu trúc trên là mẫu, không phải luật bắt buộc cho mọi loại key. Có thể mở rộng có chủ đích:

```text
# Thêm tenant khi hệ thống đa khách hàng.
shop:prod:t27:orders:order:o501

# Thêm phiên bản khi biểu diễn dữ liệu thay đổi không tương thích.
shop:prod:catalog:product:v2:p42

# Thêm thành phần phụ cho những key liên quan một đối tượng.
shop:prod:checkout:cart:c817:items
shop:prod:checkout:cart:c817:total

# Key đại diện một trạng thái toàn cục của một miền, không có entity ID.
shop:prod:catalog:sync:last-success
```

Với key không gắn vào một entity, phần cuối vẫn cần là **định danh chức năng đủ rõ**, ví dụ `last-success`, `leader` hoặc `sequence`. Đừng ép thêm ID giả như `0` nếu nó không có ý nghĩa.

Chọn một thứ tự thành phần ổn định trong toàn hệ thống. Việc lúc thì dùng `shop:prod:orders:order:o501`, lúc lại dùng `orders:shop:o501:prod` khiến việc tìm key theo pattern và quản lý ownership khó hơn.

## 3. Phân định ranh giới ứng dụng và miền nghiệp vụ

**Ứng dụng** xác định ranh giới sở hữu ở mức sản phẩm/hệ thống. **Miền nghiệp vụ** xác định ranh giới dữ liệu bên trong ứng dụng hoặc giữa các bounded context cùng thuộc một hệ thống.

Ví dụ một công ty có hai hệ thống độc lập:

```text
shop:prod:billing:invoice:inv1001
crm:prod:billing:invoice:inv1001
```

Chúng có thể cùng gọi đối tượng là `invoice` và cùng dùng ID `inv1001` nhưng không có nghĩa hai bản ghi là một. Prefix `shop` và `crm` loại bỏ đụng tên.

Trong hệ thống `shop`, các miền cũng có thể trùng tên thực thể:

```text
shop:prod:identity:token:t55
shop:prod:payments:token:t55
```

Token đăng nhập và token thanh toán không có cùng ngữ nghĩa, TTL hoặc điều kiện bảo mật. Phần `domain` giúp phân biệt ngay cả khi `entity` hoặc `identity` tình cờ trùng nhau.

Trong kiến trúc microservices, có thể chọn một trong hai cách nhất quán:

- Mọi service cùng một sản phẩm dùng prefix ứng dụng thống nhất rồi thêm domain, ví dụ `shop:prod:catalog:...`.
- Các hệ thống triển khai độc lập dùng application prefix riêng, ví dụ `catalog-api:prod:...` và `payment-api:prod:...`.

Điểm cần ưu tiên là xác định **ai thực sự sở hữu quyền ghi và vòng đời dữ liệu**. Một key do dịch vụ `orders` sở hữu không nên được dịch vụ `catalog` tự ý sửa chỉ vì cả hai cùng có quyền truy cập Redis.

### Đừng đặt tên bằng tên lớp triển khai

Các tên sau dễ trở nên lỗi thời:

```text
ShopController:product:42
ProductServiceImpl:42
com.example.shop.model.Product:42
```

Chúng phụ thuộc vào cấu trúc source code và có thể quá dài. Khi đổi package hoặc refactor, những tên key cũ vẫn nằm trong Redis nhưng không còn được code mới truy cập. Nên ưu tiên ý nghĩa ổn định như `shop:prod:catalog:product:p42`.

## 4. Định danh: một đối tượng phải có một cách biểu diễn nhất quán

Phần cuối tên key xác định **bản ghi cụ thể**. Quy tắc chọn ID ảnh hưởng trực tiếp đến tính duy nhất và khả năng đọc lại dữ liệu.

Ví dụ ID sản phẩm gốc là số `42`. Nếu service A dùng `42` còn service B dùng `00042`, Redis nhìn nhận đây là hai key khác nhau:

```text
shop:prod:catalog:product:42
shop:prod:catalog:product:00042
```

Tương tự, `P42` và `p42` cũng khác nhau vì Redis key phân biệt chữ hoa/chữ thường. Một ID dạng UUID có dấu gạch nối và UUID bỏ dấu gạch nối là hai chuỗi khác nhau. Vì vậy, cần thống nhất cách canonicalize ID **ngay tại ranh giới ứng dụng**.

Những lựa chọn thường gặp:

| Loại định danh | Ví dụ | Lưu ý |
|---|---|---|
| Số nguyên nghiệp vụ | `42` | Quy định có hay không có zero padding; tránh tái sử dụng ID tùy tiện |
| UUID chuẩn | `8be0b730-85cd-4f2b-b82a-5ef09ca79e37` | Thống nhất chữ thường và dấu gạch nối |
| ULID hoặc mã ổn định | `01JC5R4M7D8VY6Q9G2PEAC7Z0M` | Phải bảo toàn định dạng canonical, không tự đổi case |
| ID đã phân biệt tenant | `t27:o501` ở các đoạn riêng | Đặt tenant trong namespace để tránh trùng ID giữa tenant |
| Email hoặc tên người dùng | `an@example.com` | Không nên đưa thông tin cá nhân vào tên key; dùng opaque ID |

Định danh dùng cho key cần đủ ổn định trong thời gian tồn tại dữ liệu. Nếu dùng username có thể đổi thay cho user ID bất biến, mỗi lần đổi username có thể để lại key cũ hoặc tạo ra hai phiên bản cùng tồn tại.

### Tách ID người dùng khỏi dữ liệu cá nhân

Không nên viết:

```text
shop:prod:identity:session:an@example.com
shop:prod:customer:profile:+84901234567
shop:prod:auth:token:eyJhbGciOi...
```

Tên key có thể xuất hiện trong command trace, metrics, bản sao lưu và công cụ quản trị. Thay vào đó:

```text
shop:prod:identity:session:s912
shop:prod:customer:profile:u42
shop:prod:auth:token-ref:trf928
```

Các ID này phải do hệ thống tạo/quản lý và không tiết lộ secret. Khi cần tra cứu theo email hoặc số điện thoại, xử lý qua tầng dữ liệu/ánh xạ có kiểm soát và không để thông tin nhạy cảm xuất hiện tùy tiện trong key.

## 5. Chọn quy tắc ký tự và độ dài tên key

Redis cho phép key chứa dữ liệu nhị phân và không giới hạn tên key chỉ ở ASCII. Tuy nhiên, đối với hệ thống nhiều service và cần thao tác vận hành, **key dạng văn bản UTF-8 có cấu trúc dễ hiểu** thường là lựa chọn thuận tiện.

Quy ước đề xuất:

- Dùng chữ thường cho các phần do hệ thống kiểm soát như `shop`, `prod`, `catalog`, `product`.
- Dùng dấu `:` để phân tách các thành phần; dùng dấu `-` bên trong một thành phần ghép từ, ví dụ `rate-limit`.
- Chuẩn hóa định danh theo hợp đồng nguồn; tránh tùy tiện hạ chữ thường một ID phân biệt case.
- Không để giá trị `null`, chuỗi rỗng hoặc khoảng trắng thành một đoạn key mà không có ý nghĩa rõ ràng.
- Không ghép trực tiếp chuỗi do người dùng nhập vào key nếu nó có thể chứa dấu phân tách hoặc ký tự điều khiển; cần xác thực hoặc mã hóa đoạn ID bằng một quy tắc xác định.
- Giữ key ngắn vừa đủ để vận hành; phần prefix quá dài và lặp hàng triệu lần sẽ tiêu tốn bộ nhớ và băng thông.

Ví dụ dấu phân tách nằm trong ID có thể làm cấu trúc tên key khó đọc:

```text
shop:prod:catalog:product:region:42
```

Ở đây `region:42` là một ID hay hai thành phần khác nhau? Quy ước ứng dụng phải quyết định. Nếu ID có thể chứa bất kỳ ký tự nào, hãy mã hóa **chỉ đoạn ID** bằng cách ổn định, chẳng hạn Base64 URL-safe không padding, hoặc dùng ID opaque do hệ thống cấp. Bên đọc phải giải mã theo cùng hợp đồng; không dùng cách mã hóa thay đổi giữa phiên bản triển khai.

**Độ dài key:** Redis cho phép key dài, nhưng key rất dài gây overhead bộ nhớ, network và logging. Một key `shop:prod:catalog:product:p42` dài hơn `p42`, đổi lại việc vận hành và tránh đụng tên rõ ràng hơn. Đừng tối ưu đến mức bỏ mất thông tin ownership, nhưng cũng tránh nhúng JSON, stack trace hoặc payload dài trong tên key.

## 6. Đặt tên theo loại dữ liệu Redis và mục đích truy cập

Một entity nghiệp vụ có thể được lưu theo nhiều mô hình: Redis string chứa JSON, Redis hash với nhiều field, Redis set chứa ID liên quan, Redis sorted set chứa thứ hạng, v.v. Tên key nên truyền tải **mục đích và cấu trúc logic**, dù không nhất thiết phải lặp lại từ `string` hay `hash` trong tên.

Ví dụ cho hệ thống bán hàng:

| Key | Redis type | Nội dung | Vòng đời gợi ý |
|---|---|---|---|
| `shop:prod:catalog:product:p42` | String | JSON thông tin sản phẩm đã cache | Có TTL theo chính sách cache |
| `shop:prod:checkout:cart:c817` | Hash | Các field giỏ hàng hiện tại | TTL phiên giỏ hàng |
| `shop:prod:identity:session:s912` | String hoặc Hash | Trạng thái phiên | TTL ngắn theo chính sách session |
| `shop:prod:catalog:popular-products` | Sorted set | ID sản phẩm và điểm xếp hạng | Cập nhật theo chiến lược thống kê |
| `shop:prod:orders:pending-ids` | Set | Tập ID đơn chờ xử lý | Phụ thuộc nghiệp vụ, không xóa tùy tiện |
| `shop:prod:limits:user:u42` | String | Counter áp hạn mức cho user | TTL theo cửa sổ giới hạn |

Những loại Redis trên chỉ là lựa chọn thiết kế minh họa, không phải Redis tự chọn kiểu từ tên key. Khi có nhiều phép truy cập khác nhau trên cùng một thực thể, có thể thêm hậu tố để phân biệt các key liên quan:

```text
shop:prod:checkout:cart:c817:items
shop:prod:checkout:cart:c817:total
shop:prod:checkout:cart:c817:updated-at
```

Tuy nhiên, nếu ba giá trị là những field của **cùng một Redis hash**, chúng có thể dùng một Redis key `shop:prod:checkout:cart:c817` và các hash field `items`, `total`, `updatedAt`. Không nên tạo nhiều key chỉ vì có nhiều thuộc tính Java. Hãy chọn mô hình lưu trữ trước, sau đó đặt tên phù hợp với mô hình đó.

### Tránh dùng cùng một key cho nhiều kiểu Redis

Ví dụ:

```redis
SET shop:prod:catalog:product:p42 '{"name":"Notebook"}'
HSET shop:prod:catalog:product:p42 price 120000
```

Lệnh `HSET` không tương thích với key hiện đang có Redis type là string và thường trả về lỗi `WRONGTYPE Operation against a key holding the wrong kind of value`.

Nếu muốn thay từ JSON string sang Redis hash, hãy coi đó là thay đổi schema/lifecycle của key. Có thể dùng tên mới có version để chuyển đổi có kiểm soát thay vì cố dùng lại key cũ trong lúc hai phiên bản ứng dụng cùng chạy.

## 7. Môi trường triển khai: `dev`, `staging`, `prod`

Nếu các môi trường chạy trên cùng Redis instance hoặc Cluster (chủ yếu phù hợp với tình huống thử nghiệm có kiểm soát), prefix môi trường giúp giảm nguy cơ đụng key:

```text
shop:dev:catalog:product:p42
shop:staging:catalog:product:p42
shop:prod:catalog:product:p42
```

Nhờ đó, thao tác `SET` của môi trường dev không trực tiếp ghi đè tên key của môi trường prod. Tuy nhiên, **prefix không tạo cách ly về CPU, RAM, network, chính sách eviction hoặc quyền truy cập**. Một môi trường dev ghi quá nhiều key vẫn có thể gây áp lực lên Redis dùng chung với production.

Nếu production cần tính sẵn sàng, kiểm soát truy cập và giới hạn tài nguyên độc lập, nên cấp **Redis deployment riêng**. Prefix môi trường khi đó vẫn có ích để minh bạch nguồn dữ liệu, nhưng không phải cơ chế bảo vệ chính.

Không hard-code `prod` trong source rồi deploy cùng artifact sang staging. Nên đưa phần application/environment vào một cấu hình do deployment cung cấp và tạo key tập trung ở tầng lưu trữ.

## 8. Multi-tenancy: thêm tenant khi định danh không duy nhất toàn hệ thống

Trong SaaS, mỗi khách hàng (tenant) có thể sở hữu `orderId` giống nhau. Nếu chỉ đặt key theo order ID:

```text
shop:prod:orders:order:501
```

thì hai tenant cùng có đơn hàng `501` sẽ trùng nhau. Có thể đưa tenant vào một vị trí nhất quán:

```text
<application>:<environment>:<tenant>:<domain>:<entity>:<identity>

shop:prod:t27:orders:order:501
shop:prod:t91:orders:order:501
```

Tenant ID nên là một định danh ổn định do hệ thống cấp, không nhất thiết là tên công ty có thể đổi. Khi app không có multi-tenancy, tránh chèn đoạn `tenant:default` vào mọi key chỉ vì dự đoán tương lai.

Điều quan trọng là **tenant phải được xác định từ ngữ cảnh xác thực/ủy quyền đáng tin cậy**. Không nhận một chuỗi tenant từ request rồi tùy ý tạo key để đọc dữ liệu tenant khác. Prefix là công cụ tổ chức tên key; quyền truy cập phải được kiểm soát ở tầng ứng dụng và có thể bổ sung Redis ACL/credential riêng khi phù hợp.

### Tenant và chính sách xóa dữ liệu

Có namespace theo tenant sẽ giúp lập danh sách key cần đánh giá khi xóa dữ liệu của tenant:

```text
shop:prod:t27:orders:*
shop:prod:t27:checkout:*
shop:prod:t27:identity:*
```

Nhưng không được xem wildcard là một thao tác xóa an toàn tuyệt đối. Ngoài key trực tiếp, hệ thống có thể có index phụ, stream, delayed-job, cache dùng chung, repository metadata và những key khác không theo mẫu trên. Quy trình xóa tenant phải biết **mọi thành phần sở hữu dữ liệu**, yêu cầu lưu giữ và khả năng dữ liệu đang được ghi đồng thời.

## 9. Ví dụ Java: một lớp tạo key thống nhất

Spring Data Redis không buộc ứng dụng đặt tên key theo một schema duy nhất. Để tránh ghép chuỗi rải rác trong nhiều service, có thể tạo một lớp chuyên tạo key.

Ví dụ cấu hình ứng dụng:

```yaml
# application.yml
app:
  redis:
    namespace: shop:dev

spring:
  data:
    redis:
      host: localhost
      port: 6379
```

`app.redis.namespace` là **thuộc tính tự định nghĩa của ứng dụng**, không phải một thuộc tính chuẩn có sẵn của Spring Data Redis. Cấu hình connection Redis vẫn thuộc `spring.data.redis.*`.

Lớp tạo key:

```java
package com.example.shop.redis;

import java.util.Objects;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class ShopRedisKeys {
    private static final Pattern ID_PATTERN =
            Pattern.compile("[A-Za-z0-9_-]+");

    private final String namespace;

    public ShopRedisKeys(@Value("${app.redis.namespace}") String namespace) {
        if (!namespace.matches("[a-z0-9-]+:[a-z0-9-]+")) {
            throw new IllegalArgumentException("Invalid Redis namespace");
        }
        this.namespace = namespace;
    }

    public String product(String productId) {
        return namespace + ":catalog:product:v1:" + segment(productId);
    }

    public String cart(String cartId) {
        return namespace + ":checkout:cart:v1:" + segment(cartId);
    }

    public String session(String sessionId) {
        return namespace + ":identity:session:v1:" + segment(sessionId);
    }

    private static String segment(String input) {
        Objects.requireNonNull(input, "Redis key ID cannot be null");
        if (!ID_PATTERN.matcher(input).matches()) {
            throw new IllegalArgumentException("Invalid Redis key ID");
        }
        return input;
    }
}
```

Ví dụ này chọn chính sách **từ chối** ID chứa ký tự không thuộc tập cho phép, giúp cấu trúc key không bị thay đổi bởi dấu `:` hoặc ký tự điều khiển trong input. Nếu ID nghiệp vụ có dạng UUID với dấu `-`, biểu thức trên chấp nhận; nếu ID là email, chuỗi có dấu `:` hoặc Unicode, cần thống nhất cách mã hóa canonical trước khi gọi key builder thay vì bỏ kiểm tra. Không có một regex chung phù hợp cho mọi hệ thống.

Khi đổi môi trường:

```text
app.redis.namespace=shop:staging
    product("p42") -> shop:staging:catalog:product:v1:p42

app.redis.namespace=shop:prod
    product("p42") -> shop:prod:catalog:product:v1:p42
```

Service lưu và đọc dữ liệu chỉ cần gọi cùng một key builder:

```java
package com.example.shop.redis;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheStore {
    private final StringRedisTemplate redis;
    private final ShopRedisKeys keys;

    public ProductCacheStore(StringRedisTemplate redis, ShopRedisKeys keys) {
        this.redis = redis;
        this.keys = keys;
    }

    public void cacheJson(String productId, String productJson) {
        redis.opsForValue().set(
                keys.product(productId),
                productJson,
                Duration.ofMinutes(15));
    }

    public String findJson(String productId) {
        return redis.opsForValue().get(keys.product(productId));
    }

    public Boolean remove(String productId) {
        return redis.delete(keys.product(productId));
    }
}
```

Đây là cache JSON dạng Redis string, với `StringRedisTemplate` lưu value là chuỗi UTF-8. Đoạn code không tự kiểm tra JSON hoặc chuyển DTO; nếu ứng dụng thao tác Java object, hãy cấu hình serializer phù hợp ở template tương ứng. Hàm `remove` trả `Boolean` vì API `delete` có thể trả `null` ở một số ngữ cảnh như pipeline/transaction.

Lợi ích của lớp tạo key tập trung là có thể thay một quy tắc, kiểm tra đầu vào hoặc đổi version namespace tại một nơi. Tuy nhiên, đổi key builder khi dữ liệu cũ đã tồn tại vẫn là **thay đổi hợp đồng lưu trữ**, cần chiến lược đọc dữ liệu cũ hoặc di trú, không thể coi là refactor code thuần túy.

## 10. Spring Cache: tên cache và cache prefix cũng là namespace

Spring Cache với Redis có thể tạo key từ **cache name** và **cache key**. Ví dụ:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public Product findProduct(String productId) {
    // ... đọc dữ liệu từ nguồn chính
}
```

Tên key vật lý do `RedisCacheConfiguration` và cơ chế key serialization tạo ra. Với cấu hình mặc định phổ biến, có prefix dựa trên cache name, ví dụ `products::p42`. Nếu nhiều ứng dụng cùng dùng cache tên `products` trên một Redis, chúng vẫn có nguy cơ đụng key nếu prefix không chứa thông tin sở hữu.

Có thể cấu hình namespace riêng cho cache:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

@Configuration(proxyBeanMethods = false)
public class RedisCacheNamingConfig {

    @Bean
    RedisCacheConfiguration redisCacheConfiguration(
            @Value("${app.redis.namespace}") String namespace) {

        return RedisCacheConfiguration.defaultCacheConfig()
                .computePrefixWith(cacheName ->
                        namespace + ":cache:" + cacheName + "::");
    }
}
```

Ví dụ cache `products` với key `p42` có prefix:

```text
shop:prod:cache:products::p42
```

Đây là cấu hình tên key theo **Spring Cache**, độc lập với cách `ShopRedisKeys.product(...)` dùng cho `StringRedisTemplate`. Không tự động trộn hai quy tắc thành cùng một key nếu chúng lưu payload khác nhau.

Nếu muốn phản ánh miền nghiệp vụ rõ hơn, có thể đặt cache name như `catalog-products` rồi quy định:

```text
shop:prod:cache:catalog-products::p42
shop:prod:cache:identity-users::u42
```

Tên cache nên cố định và có chủ sở hữu. Không tắt key prefix khi nhiều cache chia sẻ Redis nếu chưa có thiết kế tránh trùng key. Cần kiểm tra cache key generator, serializer và TTL bên cạnh prefix; prefix chỉ giải quyết một phần của bài toán.

## 11. Redis Repository: `@RedisHash` tạo key theo keyspace riêng

Spring Data Redis Repository lưu entity qua cơ chế mapping, thường dưới dạng Redis hash. Annotation `@RedisHash` xác định keyspace của entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("catalog:product")
public class ProductRedisEntity {
    @Id
    private String id;
    private String name;

    // Constructor, getter và setter phù hợp.
}
```

Với ID `p42`, keyspace kiểu `catalog:product` thông thường tạo Redis key có dạng:

```text
catalog:product:p42
```

**Quan trọng:** `@RedisHash("catalog:product")` là cấu hình keyspace của repository; nó **không tự gắn** `app.redis.namespace=shop:prod` từ ví dụ key builder hoặc lấy prefix do `RedisCacheConfiguration` khai báo. Vì vậy, nếu các môi trường chia sẻ Redis, repository cũng phải có chiến lược keyspace riêng phù hợp với môi trường và vòng đời dữ liệu.

Không nên giả định rằng đổi tên một `RedisTemplate` bean hay cấu hình `keySerializer` sẽ làm repository tự đổi keyspace. Redis Repository có cơ chế mapping, RedisKeyValueAdapter và metadata riêng; các key phụ phục vụ index hoặc quan hệ có thể do framework sinh ra theo quy tắc khác với key chính. Cần xem toàn bộ phạm vi dữ liệu repository quản lý khi thiết kế namespace, backup hoặc xóa dữ liệu.

Khi cần keyspace động theo môi trường, hãy sử dụng điểm cấu hình keyspace/mapping context được Spring Data Redis hỗ trợ trong phiên bản dự án, hoặc cách tổ chức Redis deployment riêng. Tránh hard-code `prod` vào annotation rồi dùng nguyên class trong staging nếu cả hai môi trường dùng chung Redis.

## 12. Spring Session và các thành phần tạo key ngoài code nghiệp vụ

Không chỉ code gọi `RedisTemplate` mới ghi key. Các thư viện có thể tự quản lý key, ví dụ:

- **Spring Session**: key session và metadata/index theo namespace riêng của Spring Session.
- **Spring Cache**: key theo cache name và cache key, do Redis Cache configuration tạo.
- **Spring Data Redis Repository**: keyspace entity và key phụ phục vụ mapping/index.
- **Bộ giới hạn tần suất hoặc distributed lock**: key theo resource/action/owner, có quy tắc TTL và giá trị rất riêng.
- **Message stream/consumer group**: stream là Redis key; tên consumer group là định danh trong stream, không đồng nghĩa với một Redis key riêng.

Do đó, một hệ thống dùng chung Redis phải có **bảng sở hữu các nhóm key**, gồm cả những key do framework và thư viện tạo ra. Với Spring Session, các phiên bản Spring Boot/Spring Session có thuộc tính cấu hình namespace, chẳng hạn `spring.session.redis.namespace`; cần đối chiếu đúng phiên bản khi sử dụng. Không nên lấy namespace `app.redis.namespace` tự tạo rồi mặc định mọi thư viện đều đọc thuộc tính này.

Khi nâng cấp thư viện, cấu trúc key và metadata có thể thay đổi. Dữ liệu session hoặc repository đang tồn tại cần được xem xét tương thích trước khi đổi quy tắc tên key hoặc serialization.

## 13. Tên key và Redis Cluster: hash slot không dựa trên dấu `:`

Redis Cluster phân phối key qua **16.384 hash slot**. Client và Redis xác định slot từ byte của key; các dấu `:` trong namespace không tạo ra shard hoặc giới hạn key vào một node.

Hai key cùng prefix vẫn có thể nằm ở hai slot khác nhau:

```text
shop:prod:checkout:cart:c817
shop:prod:checkout:cart:c818
```

Redis Cluster có cú pháp **hash tag**: nếu key có cặp `{...}` hợp lệ, phần bên trong dấu ngoặc được dùng khi tính hash slot. Ví dụ muốn hai key gắn với cùng một giỏ hàng được xử lý đa key trên cùng slot:

```text
shop:prod:checkout:cart:{c817}:items
shop:prod:checkout:cart:{c817}:total
```

Hai key trên có cùng hash tag `c817`, nên cùng slot. Điều này hữu ích khi có lệnh hoặc transaction nhiều key cần cùng slot. Tuy nhiên:

- Không phải mọi key cùng ứng dụng/domain đều cần chung slot.
- Đặt hash tag rộng như `{shop}` cho toàn bộ hệ thống có thể dồn tải về một slot/node và phá mục tiêu phân phối tải của Cluster.
- Hash tag **không tạo một logical database riêng**, cũng không tạo ranh giới bảo mật.
- Khi dùng multi-tenancy, hash tag cho nhóm cần thao tác cùng nhau nên chứa định danh đủ duy nhất trong ngữ cảnh (ví dụ tenant và cart) nếu ID giỏ hàng có thể trùng giữa tenant.

Ví dụ kiểm tra slot trên môi trường Cluster thử nghiệm:

```bash
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT \
  'shop:prod:checkout:cart:{c817}:items'

redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT \
  'shop:prod:checkout:cart:{c817}:total'
```

Hai lệnh sẽ trả cùng số slot. Địa chỉ `redis-node-1` chỉ minh họa; cần thay bằng endpoint thật của môi trường thử nghiệm.

### Serializer của key ảnh hưởng slot

`StringRedisTemplate` thường mã hóa key theo UTF-8. Nếu một `RedisTemplate` khác dùng JDK serialization cho key, hai object Java có cùng `toString()` chưa chắc tạo ra cùng byte key; Cluster cũng có thể tính slot khác. Khi nhiều client và nhiều ngôn ngữ cần chia sẻ key, hãy **thống nhất serializer key và quy ước encoding**. Tên key bạn thấy trong Java phải tương ứng với byte mà Redis thực sự nhận được.

## 14. Namespace và Redis logical database là hai khái niệm khác nhau

Redis standalone có thể hỗ trợ nhiều logical database, được chọn bằng `SELECT`. Nhưng trong Redis Cluster chỉ có database số `0`. Namespace theo tên key hoạt động trên cả hai topology:

```text
DB 0 / Cluster keyspace
    shop:prod:catalog:product:p42
    shop:prod:orders:order:o501
    billing:prod:invoice:inv1001
```

Chọn DB 1 hoặc DB 2 không thay thế yêu cầu thiết kế key có ý nghĩa. Khi chuyển standalone sang Cluster, các DB ngoài 0 không còn được hỗ trợ; nếu từng phân tách service chỉ bằng database index, cần đưa thông tin sở hữu vào tên key và xây dựng kế hoạch di trú.

Ví dụ trước đây:

```text
Standalone DB 1: user:42  -> dữ liệu identity
Standalone DB 2: user:42  -> dữ liệu checkout
```

Khi chuyển về Cluster DB 0, không thể giữ nguyên hai tên `user:42`. Một mapping mới có thể là:

```text
shop:prod:identity:profile:u42
shop:prod:checkout:cart:u42
```

Namespace làm rõ ý nghĩa và tránh trùng key; nó không bảo đảm mỗi nhóm có RAM, CPU hay khả năng failover riêng. Nếu cần cách ly mạnh, phải tách hạ tầng và chính sách truy cập phù hợp.

## 15. Tên key, TTL và vòng đời dữ liệu

Đặt tên key đúng còn cần xác định **key tồn tại bao lâu và ai được xóa**. Một session có TTL 30 phút khác với đơn hàng cần lưu dài hạn; không nên chỉ nhìn vào dạng `shop:prod:...` rồi áp cùng TTL cho tất cả.

Ví dụ:

```text
shop:prod:catalog:product:v1:p42      -> cache, TTL 15 phút
shop:prod:identity:session:v1:s912    -> session, TTL 30 phút
shop:prod:limits:user:u42             -> giới hạn request, TTL theo cửa sổ
shop:prod:orders:order:o501           -> dữ liệu nghiệp vụ, theo chính sách lưu giữ
```

Một Redis key có thể không có TTL hoặc có TTL đã đặt. Trong Redis, `TTL` trả về:

```text
> 0 : số giây còn lại (thực tế có thể bằng 0 khi gần hết hạn)
-1  : key tồn tại nhưng không có thời hạn hết hạn
-2  : key không tồn tại
```

Lưu ý `SET key value` không kèm tùy chọn giữ TTL thông thường sẽ **loại bỏ TTL hiện có** của key. Trong Spring Data Redis, khi ghi cache nên chỉ định TTL tường minh:

```java
redis.opsForValue().set(
        keys.product("p42"),
        productJson,
        Duration.ofMinutes(15));
```

Redis hash, set hoặc sorted set cũng có TTL ở **cấp Redis key**. Nếu một Redis hash chứa 10 field thì việc đặt TTL cho hash không có nghĩa mỗi field được cấp TTL độc lập theo mặc định. Khi một object có nhiều Redis key phụ, cần quyết định chúng sẽ được gia hạn, xóa hoặc tái tạo thế nào để tránh orphan key.

### Đừng dùng key cache làm nguồn sự thật nghiệp vụ khi chưa thiết kế cho điều đó

Ví dụ, `catalog:product` có thể chỉ là cache và được tạo lại từ database chính; mất key này làm tăng latency nhưng không làm mất dữ liệu nguồn. Ngược lại, nếu số dư, đơn hàng hoặc lịch sử giao dịch chỉ lưu trong Redis, thay đổi TTL hoặc eviction policy có thể gây hậu quả lớn. Quy tắc đặt tên nên đi cùng tài liệu về mức độ quan trọng và vòng đời dữ liệu.

## 16. Debug và quan sát theo prefix

Namespace giúp điều tra sự cố khi có hàng triệu key. Ví dụ muốn biết loại dữ liệu, TTL và giá trị một key trong môi trường được phép:

```bash
redis-cli TYPE shop:prod:catalog:product:v1:p42
redis-cli TTL shop:prod:catalog:product:v1:p42
redis-cli EXISTS shop:prod:catalog:product:v1:p42

# Chỉ dùng GET nếu TYPE cho biết đây là Redis string.
redis-cli --raw GET shop:prod:catalog:product:v1:p42
```

Muốn duyệt dần các key có prefix trong Redis standalone:

```bash
redis-cli --scan --pattern 'shop:prod:catalog:*'
```

`SCAN` phân trang quá trình duyệt key, phù hợp hơn lệnh `KEYS shop:prod:catalog:*` khi Redis có nhiều key. Nhưng SCAN **không phải snapshot nhất quán**: trong khi quét, các key có thể được tạo/xóa, và cùng key có thể được trả về nhiều lần. Một công cụ tổng hợp phải xử lý duplicate và kiểm soát các thay đổi đồng thời.

Trong Redis Cluster, `SCAN` trên một node chỉ duyệt key thuộc node đó. Dùng `redis-cli -c` không tự biến một lần `SCAN` thành quét toàn bộ Cluster; nếu cần thống kê toàn cụm, phải dùng công cụ hiểu topology và duyệt các primary tương ứng.

### Không xóa hàng loạt chỉ dựa trên prefix

Lệnh `DEL`, `UNLINK`, `FLUSHDB` hoặc script xóa theo pattern đều có thể gây mất dữ liệu. Dù key bắt đầu bằng `shop:dev:`, có thể vẫn có dữ liệu quan trọng hoặc job đang sử dụng key đó. Trước khi thực hiện xóa hàng loạt, quy trình vận hành phải xác minh owner, môi trường, tính chất key, ảnh hưởng ứng dụng và các key phụ.

Không dùng `KEYS *` rồi xóa toàn bộ kết quả trong một script production. Với lượng lớn dữ liệu, cần duyệt có giới hạn và dùng thao tác phù hợp với chính sách vận hành. `UNLINK` có thể giúp giải phóng bộ nhớ bất đồng bộ cho key được xóa, nhưng bản thân nó vẫn là thao tác xóa dữ liệu.

## 17. Namespace hỗ trợ ACL nhưng không tự tạo bảo mật

Redis ACL có thể giới hạn những tên key mà một user được phép truy cập dựa trên pattern. Namespace như `shop:prod:catalog:*` có thể giúp mô tả vùng dữ liệu của một service dễ hơn.

Ví dụ về ý tưởng phân quyền:

```text
Catalog service  -> chỉ được thao tác key shop:prod:catalog:*
Checkout service -> chỉ được thao tác key shop:prod:checkout:*
```

Nhưng prefix tự thân **không ngăn service A đọc key của B** nếu cả hai đang dùng cùng credential có quyền truy cập rộng. Nếu cần enforcement, phải cấp tài khoản/ACL hợp lệ và kiểm soát kết nối. Trong Redis Cluster cần bảo đảm chính sách xác thực/phân quyền được áp dụng nhất quán cho các node theo cách vận hành Cluster của hệ thống.

Hơn nữa, ACL của Redis không thay thế ủy quyền nghiệp vụ: một user trong tenant A không được đọc đơn của tenant B chỉ vì ứng dụng có thể truy cập cả hai key trong Redis. Việc xác định quyền phải thực hiện dựa trên principal và tenant context của request trước khi tạo tên key để đọc dữ liệu.

Không đưa password, access token hoặc dữ liệu cá nhân vào key với suy nghĩ rằng Redis chỉ ở mạng nội bộ. Tên key có thể bị ghi log, xuất hiện trong backup và lệnh giám sát.

## 18. Thay đổi quy tắc tên key là một cuộc di trú

Giả sử phiên bản đầu tiên lưu cache với key:

```text
product:p42
```

Phiên bản tiếp theo muốn dùng key giàu ngữ cảnh hơn:

```text
shop:prod:catalog:product:v2:p42
```

Nếu triển khai code mới mà không có kế hoạch, ứng dụng có thể không thấy dữ liệu cũ và tự tạo lại dữ liệu; key cũ vẫn nằm trong Redis cho tới khi hết TTL hoặc được xóa. Với cache có thể tái tạo, đây có thể là hành vi được chấp nhận. Với dữ liệu nghiệp vụ quan trọng, không thể bỏ qua dữ liệu cũ như vậy.

Một chiến lược chuyển đổi có kiểm soát:

1. **Kiểm kê** key cũ: prefix, Redis type, value serializer, TTL, owner, số lượng ước tính và nơi đang đọc/ghi.
2. **Định nghĩa hợp đồng key mới**: thứ tự thành phần, ID canonical, version khi cần và format payload.
3. **Triển khai reader tương thích**: ưu tiên đọc key mới; nếu chưa có thì đọc key cũ bằng đúng serializer cũ, chuyển/ghi lại theo key mới khi hợp lệ.
4. **Kiểm soát việc ghi đồng thời**: nếu vẫn còn phiên bản app cũ ghi key cũ, quyết định rõ dual-write, thời điểm cắt ghi hoặc khoảng downtime phù hợp.
5. **Giữ ý nghĩa TTL**: nếu key cũ chỉ còn 3 phút, không tự gia hạn thành 24 giờ trừ khi đó là quyết định nghiệp vụ. Dùng `PTTL`/TTL còn lại và handling trường hợp `-1`, `-2` khi triển khai migration.
6. **Quan sát và loại bỏ đường cũ**: theo dõi lượng read fallback, lỗi deserialize, key chưa chuyển, rồi tắt writer cũ và dọn dữ liệu theo quy trình được duyệt.

Mô hình dual-read minh họa:

```text
read(productId)
    |
    +-- GET shop:prod:catalog:product:v2:<id>
    |       |
    |       +-- có giá trị hợp lệ -> trả về
    |
    +-- GET product:<id> bằng serializer cũ
            |
            +-- có giá trị -> chuyển sang format mới
            |                 và ghi key v2 theo TTL phù hợp
            +-- không có   -> cache miss / đọc nguồn chính
```

Nếu nhiều version ứng dụng cùng chạy, cần xác định dữ liệu nào là nguồn sự thật để tránh phiên bản cũ ghi đè bản mới hoặc cập nhật bị mất. Kế hoạch migration không chỉ là đổi prefix trong helper Java.

### Có nên thêm `v1` vào tất cả key?

Không bắt buộc. Version trong key hữu ích khi thay đổi **không tương thích** như chuyển Redis string sang hash, thay cấu trúc payload hoặc cần chạy song song hai schema. Với key chỉ là counter tạm thời có TTL vài giây, version có thể không mang thêm giá trị. Điều quan trọng là có **chính sách thống nhất về cách thay đổi schema**, không phải máy móc gắn `v1` vào mọi key.

## 19. Các phản ví dụ và cách sửa

| Cách đặt tên dễ gây vấn đề | Vấn đề | Cách làm rõ hơn |
|---|---|---|
| `user:42` | Không biết application/domain | `shop:prod:identity:profile:u42` |
| `prod:42` | Không biết kiểu thực thể | `shop:prod:catalog:product:p42` |
| `com.example.Product:42` | Phụ thuộc package/class Java | `shop:prod:catalog:product:p42` |
| `shop:prod:user:an@example.com` | Để lộ thông tin cá nhân | `shop:prod:identity:profile:u42` |
| `shop:prod:cart:null` | ID không hợp lệ bị ghép chuỗi | Từ chối ID null và xác thực tại key builder |
| `shop:prod:cart:42` cho mọi tenant | Dễ trùng khi ID chỉ unique trong tenant | `shop:prod:t27:checkout:cart:42` |
| `shop:prod:{shop}:catalog:p42` | Hash tag quá rộng trong Cluster | Không dùng hash tag khi không cần, hoặc tag theo nhóm đa key |
| `shop:prod:catalog:product:p42` vừa JSON string vừa hash | Mâu thuẫn Redis type | Dùng schema/version key mới và di trú |
| `serviceA:key` nhưng mọi service dùng credential rộng | Namespace không tự bảo vệ dữ liệu | Thêm ACL/ủy quyền và chính sách ownership |

Những ví dụ trên không yêu cầu mọi ứng dụng phải chọn đúng cùng tên `shop:prod:...`; mục tiêu là đặt ra một **cấu trúc ổn định và giải thích được** trong phạm vi hệ thống thực tế.

## 20. Bài thực hành với `StringRedisTemplate` và Redis CLI

Giả sử ứng dụng `shop`, môi trường `dev`, có hai domain `catalog` và `checkout`. Ta muốn tạo hai key khác nhau nhưng cùng ID `42`:

```text
shop:dev:catalog:product:42
shop:dev:checkout:cart:42
```

Trên Redis standalone thử nghiệm:

```bash
redis-cli SET shop:dev:catalog:product:42 '{"name":"Notebook"}' EX 60
redis-cli SET shop:dev:checkout:cart:42 '{"items":2}' EX 120

redis-cli --raw GET shop:dev:catalog:product:42
redis-cli --raw GET shop:dev:checkout:cart:42

redis-cli TTL shop:dev:catalog:product:42
redis-cli TTL shop:dev:checkout:cart:42

redis-cli --scan --pattern 'shop:dev:*'
```

Hai key không va chạm tên dù đều có `identity=42`, và mỗi key có TTL độc lập. Lưu ý ở ví dụ này cả hai Redis key đều là **string chứa JSON**; không dùng `HGET` vì không phải Redis hash.

Nếu đổi `shop:dev:catalog:product:42` sang `shop:dev:catalog:product:v2:42`, lệnh `GET` trên tên mới sẽ không tự đọc được key cũ. Đó là một minh họa trực tiếp rằng tên key chính là định danh lưu trữ.

### Câu hỏi tự kiểm tra

1. Vì sao `user:42` có nguy cơ trùng key khi nhiều service cùng dùng Redis?
2. Nếu `orderId=501` chỉ duy nhất trong phạm vi từng tenant, cần đưa thành phần nào vào key?
3. Prefix `shop:prod:` có tự tạo Redis database hoặc giới hạn quyền truy cập không?
4. Vì sao hai key chung prefix `shop:prod:checkout:` chưa chắc nằm cùng slot của Redis Cluster?
5. Đổi `@RedisHash("product")` có ảnh hưởng đến keyspace repository đang lưu không, và có tự đổi key của Spring Cache không?
6. Tại sao `SET` một key cache không kèm expiry có thể tạo ra lỗi vòng đời dữ liệu dù tên key hoàn toàn đúng?
7. Khi đổi từ `product:42` sang `shop:prod:catalog:product:v2:42`, tại sao cần xem cả serializer và TTL của key cũ?

Gợi ý: mọi câu trả lời đều liên quan tới bốn hợp đồng riêng nhưng gắn với nhau: **key namespace**, **Redis data type/payload**, **vòng đời dữ liệu** và **ranh giới quyền sở hữu**.

## 21. Kết luận

Trong Spring Data Redis, nên đặt tên key sao cho mỗi key phản ánh rõ **ứng dụng**, **môi trường nếu cần**, **miền nghiệp vụ**, **loại dữ liệu hoặc mục đích** và **định danh ổn định**. Tập trung hóa việc tạo key trong lớp lưu trữ, đồng bộ serializer của key, thống nhất prefix của Spring Cache/Redis Repository/Spring Session và quyết định TTL theo vòng đời dữ liệu giúp hệ thống tránh va chạm, dễ quan sát và dễ bảo trì.

Namespace bằng chuỗi là một quy ước thiết kế có giá trị, nhưng nó không thay thế ACL, ủy quyền nghiệp vụ hay cách ly tài nguyên. Với Redis Cluster, cần hiểu thêm hash slot và chỉ dùng hash tag khi có yêu cầu multi-key cụ thể. Khi thay đổi tên key của dữ liệu đã tồn tại, hãy xử lý như một **cuộc di trú schema** với kế hoạch tương thích, vì Redis sẽ không tự biết hai tên khác nhau cùng đại diện cho một đối tượng.
