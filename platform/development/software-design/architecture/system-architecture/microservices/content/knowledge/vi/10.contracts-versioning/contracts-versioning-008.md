# Triển khai khi nhiều phiên bản bên gửi và bên nhận cùng tồn tại

> **Nguyên tắc cốt lõi:** Trong hệ thống microservices, tại thời điểm triển khai không thể giả định mọi service, mọi worker, mọi client và mọi bản sao dữ liệu sẽ cùng chuyển sang một phiên bản. Thiết kế hợp đồng (contract) phải cho phép **phiên bản cũ và mới cùng tồn tại trong khoảng chuyển tiếp**. Hãy triển khai thay đổi theo hướng tương thích trước, chuyển từng consumer và producer, quan sát thực tế, rồi mới loại bỏ phần cũ khi có bằng chứng không còn người sử dụng.

Bài học nằm trong nhóm **Hợp đồng và phiên bản** của kiến trúc microservices. Trọng tâm là **hành vi chạy đồng thời nhiều phiên bản** khi rolling deployment, canary release, blue/green, thay đổi API, nâng schema event, chuyển dữ liệu hoặc hỗ trợ mobile client chưa cập nhật. Một API có nhãn /v2 không tự làm quá trình chuyển đổi an toàn; điều quyết định là mọi cặp phiên bản có thể gặp nhau trong thực tế được xử lý đúng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao trong một lần release luôn có thể xuất hiện producer cũ, producer mới, consumer cũ và consumer mới.
2. Phân biệt **backward compatibility**, **forward compatibility**, **deployment compatibility** và **semantic compatibility**.
3. Xây ma trận các cặp phiên bản đang tồn tại của bên gửi và bên nhận; xác định phạm vi cần hỗ trợ.
4. Thiết kế thay đổi API REST/JSON, hợp đồng gRPC/Protobuf và event schema theo hướng thêm trước, di chuyển sau, xóa cuối.
5. Lập quy trình triển khai **expand → migrate → contract** không cần cập nhật đồng thời tất cả service.
6. Xử lý message tồn đọng, replay, consumer chậm, version không biết trước, rollback và dữ liệu do phiên bản mới tạo ra.
7. Kiểm thử hợp đồng và quan sát production để biết khi nào có thể ngừng hỗ trợ phiên bản cũ.
8. Phân biệt thay đổi field nhìn có vẻ tương thích với thay đổi ý nghĩa nghiệp vụ thực sự phá vỡ contract.

## 2. Vì sao nhiều phiên bản cùng tồn tại là trạng thái bình thường?

Giả sử Ordering gọi Pricing để lấy báo giá. Pricing đang có ba replica phiên bản 1.8, sẽ được rolling update lên 1.9.

~~~text
               +--------------------------+
               |        Ordering          |
               |         v3.4             |
               +-------------+------------+
                             |
                          API call
                             |
                       Load Balancer
                      /       |       \
                     v        v        v
                 Pricing  Pricing   Pricing
                   1.8      1.9       1.8
~~~

Trong khoảng cập nhật, Ordering có thể nhận phản hồi từ cả v1.8 và v1.9. Nếu Pricing 1.9 trả kiểu dữ liệu khác hoặc hiểu khác ngữ nghĩa của field, yêu cầu có thể lỗi ngẫu nhiên theo replica.

Tình huống không chỉ xảy ra trong vài phút của rollout:

- Một số pod có thể chưa cập nhật do tình trạng cluster.
- Một worker cũ có thể còn xử lý message đang chạy.
- Client mobile chỉ cập nhật khi người dùng cài phiên bản mới; một số bản có thể tồn tại nhiều tháng.
- Hệ thống đối tác có lịch phát hành độc lập và đôi khi không thể ép nâng cấp.
- Queue lưu message do producer đời cũ gửi; consumer đời mới xử lý sau.
- Một topic event có retention nhiều ngày/tháng có thể được replay bằng consumer mới.
- Một quy trình dài hạn (đơn hàng, hợp đồng, thanh toán) có thể đi qua nhiều lần deploy.
- Rollback đưa một service về bản trước, trong khi service khác hoặc dữ liệu đã ở trạng thái mới.

**Do đó, triển khai nhiều phiên bản không phải trường hợp đặc biệt; nó là điều kiện thiết kế mặc định của hệ phân tán.**

### 2.1. Producer và consumer là vai trò theo hợp đồng

**Producer** là thành phần tạo dữ liệu/thông điệp hoặc phản hồi. **Consumer** là thành phần đọc và diễn giải dữ liệu đó.

Trong REST request, client là producer của request; server là consumer của request. Khi server trả response, vai trò đổi ngược: server là producer của response, client là consumer.

Trong event-driven system, service phát event thường là producer và subscriber là consumer. Một service có thể vừa sản xuất một kiểu message vừa tiêu thụ kiểu khác.

Hãy nói rõ **loại thông điệp và hướng dữ liệu** trước khi phát biểu rằng một thay đổi “backward compatible”. Cùng một thay đổi có thể an toàn đối với response nhưng không an toàn đối với request.

## 3. Tương thích thực sự có nhiều chiều

### 3.1. Backward compatibility

Một **consumer mới** có thể xử lý dữ liệu được tạo theo phiên bản cũ, trong phạm vi đã thỏa thuận.

Ví dụ, consumer v2 cần đọc event v1 vẫn còn trong queue hoặc log. Nếu v2 chỉ hiểu một field mới mà v1 chưa từng gửi, v2 có thể thất bại khi replay.

### 3.2. Forward compatibility

Một **consumer cũ** vẫn có thể xử lý dữ liệu do producer mới tạo ra, trong phạm vi đã thỏa thuận.

Ví dụ, producer v2 thêm một field tùy chọn vào JSON response, còn client v1 bỏ qua field lạ. Nếu client v1 cấu hình fail với unknown property, thay đổi tưởng như an toàn có thể phá client.

Thuật ngữ backward/forward có cách dùng hơi khác nhau giữa công cụ và nhóm phát triển. Trong một thiết kế thực tế, nên viết **cặp phiên bản nào đọc được thông điệp nào** thay vì chỉ gắn nhãn “backward” hoặc “forward” mà không nêu hướng.

### 3.3. Schema compatibility và semantic compatibility

**Schema compatibility**: bộ phân tích có thể parse dữ liệu theo kiểu, trường, tên và cấu trúc mong đợi.

**Semantic compatibility**: dù parse được, consumer có còn hiểu **đúng ý nghĩa nghiệp vụ** không?

Ví dụ:

~~~json
// Contract cũ
{"orderStatus":"COMPLETED"}
~~~

Ở v1, COMPLETED nghĩa “khách đã nhận hàng”. Nếu v2 đổi thành “đã bàn giao cho hãng vận chuyển” nhưng giữ nguyên field và chuỗi COMPLETED, mọi parser đều chạy nhưng consumer có thể gửi thông báo sai, ghi doanh thu sai hoặc cho phép hoàn tiền sai.

**Thay đổi ý nghĩa có thể phá hợp đồng nguy hiểm hơn lỗi parse**, vì nó dễ trôi qua test kỹ thuật. Khi thay ý nghĩa, cần versioning hoặc trường/sự kiện mới với ngữ nghĩa được xác định rõ.

### 3.4. Deployment compatibility

Một release tương thích triển khai khi các **phiên bản thực sự có thể gặp nhau trong quá trình rollout và rollback** đều hoạt động đúng theo hợp đồng đã công bố.

Đây là yêu cầu khác với “code mới compile thành công” hoặc “v2 gọi v2 chạy ổn”. Cần tính cả v1 gọi v2 và v2 gọi v1, nếu cả hai cặp có thể xuất hiện trong môi trường thực.

## 4. Ma trận phiên bản: mô hình kiểm tra đơn giản nhất

Giả sử hệ thống chuyển từ Producer P1 sang P2 và Consumer C1 sang C2. Hãy lập ma trận theo dữ liệu cụ thể:

| Producer \ Consumer | C1 (cũ) | C2 (mới) |
| --- | --- | --- |
| **P1 (cũ)** | Hành vi hiện tại, thường phải giữ đúng | C2 phải đọc được P1 nếu có consumer mới trước producer hoặc còn message cũ |
| **P2 (mới)** | C1 phải hiểu được P2 nếu producer mới trước consumer hoặc còn client cũ | Hành vi mới cần kiểm thử |

Tùy thứ tự rollout và đặc điểm lưu trữ, có thể **không cần** hỗ trợ mọi tổ hợp mãi mãi. Nhưng phải chứng minh cặp nào không thể gặp nhau. Ví dụ topic Kafka lưu event P1 trong bảy ngày thì C2 dù được triển khai sau cùng vẫn có thể gặp message cũ khi replay.

### 4.1. Ví dụ ba service

~~~text
Ordering v1 -> Pricing v1 -> Promotion v1
              Pricing v2 -> Promotion v1
Ordering v1 -> Pricing v2 -> Promotion v2
Ordering v2 -> Pricing v1 -> Promotion v2
Ordering v2 -> Pricing v2 -> Promotion v2
~~~

Nếu tất cả tổ hợp trên có thể xảy ra trong một rolling update, test chỉ kịch bản toàn v2 là chưa đủ. Mỗi cạnh request/response cần có hợp đồng tương thích theo chiều dữ liệu. Khi một tính năng mới buộc Pricing v2 dùng Promotion v2, phải đặt điều kiện kích hoạt tính năng sao cho không đẩy request mới vào bản Promotion v1.

### 4.2. Phạm vi hỗ trợ không đồng nghĩa vô hạn phiên bản

Doanh nghiệp có thể quy định hỗ trợ rolling compatibility trong hai phiên bản liền kề, hoặc các client có hoạt động trong N tháng. Chính sách này phải dựa trên dữ liệu thực về thời gian rollout, retention, replay, quan hệ đối tác và hành trình người dùng. Không nên tuyên bố “chỉ hỗ trợ N-1” mà bỏ qua mobile client, message tồn đọng hoặc rollback cần N-2.

Mục tiêu là một **cửa sổ tương thích xác định và có thể đo**, không phải bảo trì mọi field từ quá khứ vĩnh viễn.

## 5. Quy tắc thay đổi hợp đồng REST/JSON

### 5.1. Thêm field tùy chọn thường an toàn hơn đổi field cũ

Contract v1:

~~~json
{
  "orderId": "O-1001",
  "status": "CONFIRMED",
  "totalMinorUnits": 390000
}
~~~

Contract v2 thêm trường:

~~~json
{
  "orderId": "O-1001",
  "status": "CONFIRMED",
  "totalMinorUnits": 390000,
  "currency": "VND"
}
~~~

Điều kiện để thay đổi an toàn:

1. Consumer v1 **cho phép field chưa biết** hoặc có phương án versioning phù hợp.
2. Field cũ vẫn có cùng ý nghĩa, kiểu và điều kiện xuất hiện.
3. Consumer v2 có cách xử lý response do producer v1 tạo ra khi currency chưa có.
4. Nếu currency bắt buộc để ra quyết định, v2 **không được tự đoán** “thiếu thì chắc chắn VND” trừ khi nghiệp vụ đã quy định đúng trong mọi trường hợp.
5. Test thực tế có cả v1/v2 theo ma trận triển khai.

Thêm trường không phải lúc nào cũng “tương thích tự động”. Parser strict, validation, JSON schema với additionalProperties=false, hash/signature payload hay contract cache có thể khiến client cũ lỗi.

### 5.2. Các thay đổi dễ phá vỡ

- Xóa hoặc đổi tên field cũ chưa được consumer chuyển.
- Chuyển kiểu number sang string hoặc object sang array.
- Đổi đơn vị tiền từ đồng sang xu nhưng giữ nguyên tên field.
- Đổi timezone, cách hiểu timestamp hoặc quy tắc làm tròn.
- Đổi trường optional thành required trong request.
- Thêm một giá trị enum mà consumer cũ xử lý bằng switch không có nhánh unknown.
- Thay đổi mã lỗi hoặc status code dẫn đến client hiểu sai kết quả.
- Biến POST idempotent thành thao tác tạo bản ghi trùng khi retry.
- Đổi thứ tự, phân trang hoặc khóa sort mà consumer đang dựa vào.
- Đổi meaning: “PAYMENT_DONE” từ “authorized” sang “captured”.

**Tương thích cần kiểm tra ở cả schema và hành vi.**

### 5.3. Response và request có hướng an toàn khác nhau

Khi **server bổ sung field vào response**, có thể triển khai producer mới trước, miễn consumer cũ chấp nhận field lạ. Consumer mới cần fallback khi gặp response server cũ.

Khi **client bổ sung field vào request**, server phải chấp nhận field đó trước khi client bắt đầu gửi, đặc biệt nếu field mới quyết định nghiệp vụ. Gửi một field mới tới server cũ vốn bỏ qua nó có thể tạo **thành công giả**: HTTP 200 nhưng quy tắc mới chưa được áp dụng.

Ví dụ client muốn checkout với requestedDeliveryWindow. Nếu server v1 bỏ qua field này, client không được mặc định người mua đã được bảo đảm đúng khung giờ. Có thể cần capability/version check, hoặc endpoint version mới với validation rõ.

### 5.4. Mở rộng thay vì đổi nghĩa một field

Muốn đổi từ field fullName sang givenName và familyName, đừng xóa fullName ngay.

Giai đoạn chuyển tiếp:

~~~json
{
  "customerId": "C-01",
  "fullName": "Nguyen Van An",
  "givenName": "An",
  "familyName": "Nguyen Van"
}
~~~

Giữ fullName cho consumer cũ, bổ sung trường mới có ngữ nghĩa rõ, cập nhật consumer theo lộ trình. Tuy nhiên việc tách tên trong nhiều ngôn ngữ không luôn chính xác; dữ liệu givenName/familyName phải được thu thập hoặc chuyển đổi theo chính sách có thể kiểm chứng, không tự áp quy tắc cắt chuỗi đơn giản cho mọi tên.

## 6. Một ví dụ Java/Spring Boot về DTO tương thích

Consumer v2 có thể cần đọc cả response đời cũ chưa có currency. Tùy chính sách, có thể làm trường mới optional trong tầng tích hợp và chỉ chuyển sang domain khi đủ thông tin.

~~~java
package example.ordering.infrastructure.pricing;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.math.BigDecimal;

// DTO ở biên tích hợp, không phải entity của miền Ordering.
@JsonIgnoreProperties(ignoreUnknown = true)
public record PriceResponseDto(
        String quoteId,
        BigDecimal amount,
        String currency
) {}
~~~

Annotation giúp client bỏ qua field mới chưa biết, nhưng không có nghĩa mọi thay đổi tương lai đều an toàn. Bên trong application, cần kiểm tra:

~~~java
package example.ordering.application;

import example.ordering.infrastructure.pricing.PriceResponseDto;

public class PriceResponseMapper {
    public ValidatedQuote toDomain(PriceResponseDto dto) {
        if (dto.quoteId() == null || dto.amount() == null) {
            throw new IllegalArgumentException("Invalid pricing response");
        }

        // Currency bắt buộc trong quyết định đặt hàng:
        // không đoán một giá trị không được contract bảo đảm.
        if (dto.currency() == null || dto.currency().isBlank()) {
            throw new UnsupportedOperationException(
                    "Pricing contract lacks required currency");
        }

        return new ValidatedQuote(
                dto.quoteId(), dto.amount(), dto.currency());
    }
}

record ValidatedQuote(
        String quoteId,
        java.math.BigDecimal amount,
        String currency) {}
~~~

Đoạn code minh họa cách **không âm thầm đoán dữ liệu quan trọng**, không phải chương trình Spring Boot hoàn chỉnh. Nếu producer v1 không cung cấp currency, một đường thích nghi an toàn khác có thể dùng hợp đồng v1 với tiền tệ được xác định bằng context và kiểm chứng; hoặc chỉ kích hoạt tính năng currency mới khi upstream bảo đảm cung cấp.

### 6.1. Strict input, tolerant reader có kiểm soát

“Bỏ qua unknown fields” có thể phù hợp cho response hoặc event khi field mới thực sự tùy chọn. Nhưng với một **command mang ý nghĩa thay đổi trạng thái**, bỏ qua field mới đôi khi gây lỗi logic nghiêm trọng.

Ví dụ CreatePaymentRequest v2 có requires3DS=true. Server v1 bỏ qua requires3DS và xử lý thanh toán như v1 sẽ nguy hiểm. Cần version/capability gate hoặc reject command không hỗ trợ.

Một chiến lược hợp lý: **đọc dữ liệu có khả năng mở rộng, nhưng xác thực chặt bất biến và yêu cầu nghiệp vụ**.

## 7. Expand – Migrate – Contract: quy trình thay đổi an toàn

Đây là khuôn mẫu chuyển tiếp khi không thể cập nhật đồng thời mọi service và schema. Nó áp dụng cho API, event, database schema và cách tiêu thụ dữ liệu.

### Giai đoạn A — Expand

Bổ sung thứ mới **mà chưa xóa thứ cũ**:

- Thêm field mới có tính tùy chọn hoặc có default hợp lệ theo nghiệp vụ.
- Cho server hiểu cả request cũ và mới nếu cần.
- Cho consumer mới đọc được dữ liệu cũ.
- Bổ sung cổng API / event schema mới mà vẫn phục vụ các client cũ.
- Thêm cột database mới kiểu nullable hoặc cấu trúc mới không phá truy vấn cũ.
- Viết contract tests cho phạm vi phiên bản có thể gặp nhau.

### Giai đoạn B — Migrate

Chuyển từng consumer/producer sang hợp đồng mới:

- Deploy reader đủ khả năng đọc hai dạng trước khi phát message dạng mới.
- Chuyển luồng đọc/ghi với feature flag, canary và quan sát.
- Backfill dữ liệu có kiểm soát nếu cần.
- Đổi consumer sang field mới, nhưng vẫn duy trì fallback theo chính sách.
- Xác minh lưu lượng thật đã đi qua đường mới và không còn lỗi.

### Giai đoạn C — Contract

Chỉ sau khi đủ bằng chứng:

- Không còn client/consumer cần field cũ trong cửa sổ hỗ trợ.
- Không còn message cũ có thể xuất hiện từ queue, retry hoặc replay.
- Rollback không còn cần chương trình cũ đọc schema đã loại bỏ.
- Đã có lịch deprecation và thông báo cho các bên tích hợp.
- Xóa field, endpoint, event alias, cột database hoặc adapter chuyển đổi cũ.

**Không xóa trong cùng release vừa bắt đầu phát field mới.** Xóa sớm là nguyên nhân phổ biến khiến rolling deployment thất bại.

## 8. Ví dụ từ đầu đến cuối: đổi tổng tiền đặt hàng

Một API Order v1 trả:

~~~json
{
  "orderId": "O-42",
  "total": 390000
}
~~~

Ở hệ thống cũ, total luôn được hiểu là tiền đồng. Product mới hỗ trợ nhiều currency và cần totalMinorUnits cùng currency.

### 8.1. Cách thay đổi dễ gây lỗi

Producer v2 chỉ trả:

~~~json
{
  "orderId": "O-42",
  "totalMinorUnits": 390000,
  "currency": "VND"
}
~~~

Consumer v1 vẫn đọc total và có thể lỗi hoặc mặc định 0. Nếu một số replica Ordering còn v1, người dùng thấy lỗi ngẫu nhiên trong rolling deploy. Nếu trả cả hai field mà ngầm đổi nghĩa total sang “đơn vị nhỏ nhất” ở nhiều currency, consumer cũ vẫn có thể tính sai.

### 8.2. Expand an toàn

- Giữ total với định nghĩa cũ **chỉ cho trường hợp mà định nghĩa vẫn đúng**.
- Bổ sung totalMinorUnits và currency, định nghĩa chính xác đơn vị và rounding.
- Với đơn đa tiền tệ không thể biểu diễn bằng contract v1, dùng contract hoặc capability mới và **không** giả vờ total v1 vẫn có cùng nghĩa.
- Cung cấp response kiểu cũ cho consumer v1 trong phạm vi hỗ trợ, và response mới cho consumer v2.
- Tạo contract tests với v1/v2, dữ liệu VND và dữ liệu currency khác.

Nếu sản phẩm cần chuyển sang đa tiền tệ mà hợp đồng v1 chỉ có thể đại diện VND, một phương án là duy trì endpoint /v1 dành cho VND và cung cấp /v2 cho nhiều currency; không ép v1 hiểu một ngữ nghĩa mà nó chưa từng biết.

### 8.3. Migrate và contract

- Chuyển client được phép sang v2 qua rollout/capability.
- Quan sát tỷ lệ sử dụng endpoint và các lỗi serialization/validation.
- Thông báo và đặt ngày ngừng hỗ trợ v1, lưu ý client mobile/đối tác không do mình kiểm soát.
- Sau khi mọi điều kiện hạ tầng, nghiệp vụ, retention và rollback đều đạt, mới ngừng trả total cũ.

## 9. Thay đổi database schema khi bản cũ và mới cùng chạy

Rolling deployment còn tạo vấn đề giữa **hai phiên bản ứng dụng và cùng một database**. Ví dụ đổi users.display_name thành users.preferred_name.

Cách làm nguy hiểm:

~~~sql
ALTER TABLE users RENAME COLUMN display_name TO preferred_name;
~~~

Nếu v1 đang chạy và vẫn SELECT display_name, ứng dụng v1 bị lỗi ngay. Một migration schema chạy trước rollout không đồng nghĩa tất cả code đã chuyển.

### 9.1. Quy trình expand

~~~sql
-- Minh họa PostgreSQL; điều kiện DDL thực tế phải phù hợp môi trường.
ALTER TABLE users ADD COLUMN preferred_name TEXT;
~~~

Sau khi thêm cột, v1 vẫn đọc display_name. v2 có thể được viết để đọc preferred_name nếu có, nếu chưa có thì dùng display_name theo logic đã quy định. Việc chọn trường chuẩn và cách cập nhật phải được thiết kế dựa trên **một chủ sở hữu dữ liệu**.

### 9.2. Backfill dữ liệu

~~~sql
UPDATE users
SET preferred_name = display_name
WHERE preferred_name IS NULL;
~~~

Đây là ví dụ cú pháp, không phải lệnh vận hành cho bảng lớn. Với production cần chia batch, tránh lock kéo dài, giám sát tốc độ và xác minh dữ liệu. Nếu tên hiển thị có quy tắc mới, backfill không đơn giản là copy cột.

### 9.3. Chuyển quyền ghi và đọc

Trong giai đoạn chuyển tiếp có thể cần:
- Một chủ sở hữu logic chuyển đổi giữa tên cũ và mới.
- Viết dữ liệu theo contract đã thống nhất, bảo đảm phiên bản cũ vẫn đọc được.
- Tránh hai ứng dụng cùng ghi hai cột theo logic mâu thuẫn.
- Chuyển reader sang preferred_name khi dữ liệu đủ đầy.
- Kiểm tra cách rollback code cũ xử lý bản ghi do code mới tạo.

**Dual write tạm thời có rủi ro**, nhất là khi hai trường có thể lệch nhau. Nếu cần, phải ghi trong cùng transaction cục bộ nơi thích hợp, có nguồn chuẩn, cơ chế kiểm tra và kế hoạch chấm dứt.

### 9.4. Contract schema

Chỉ drop display_name khi không còn bản chương trình có thể dùng cột đó, kể cả trong rollback và tác vụ nền. Dùng bằng chứng inventory phiên bản, telemetry và kết quả backfill, không dựa trên việc “đã deploy v2” một lần.

## 10. REST API versioning: /v1, /v2 và khả năng cùng tồn tại

Phiên bản endpoint là công cụ hữu ích khi thay đổi **không thể giữ tương thích trong cùng một hợp đồng**.

~~~text
GET /api/v1/orders/O-42
GET /api/v2/orders/O-42
~~~

Hai endpoint có thể cùng tồn tại và cùng đọc một nguồn dữ liệu nghiệp vụ. Nhưng:

- Hợp đồng của v1 vẫn phải giữ ngữ nghĩa đã cam kết.
- v2 có thể cung cấp mô hình mới và luật mới nếu nghiệp vụ cho phép.
- Versioning không loại bỏ nhu cầu migration database và quyền sở hữu.
- Cần chính sách deprecation, analytics theo version, tài liệu lỗi và kiểm thử.
- Không nên tạo v3 cho mọi lần thêm field tùy chọn, nếu hợp đồng hiện tại có thể tiến hóa tương thích.

Có thể version qua URL, header, media type hoặc cơ chế khác. Quan trọng là **rõ ràng, nhất quán trong hệ sinh thái và kiểm tra được đường phục vụ phiên bản cũ**.

### 10.1. Chọn khi nào phải tạo version mới

Tạo version mới khi không thể diễn đạt thay đổi bằng field mới/tùy chọn mà vẫn giữ ý nghĩa cũ, chẳng hạn:

- Thay đổi bản chất tài nguyên hoặc hành vi lệnh.
- Đổi đơn vị và rule xử lý không thể tương thích.
- Đổi lỗi/điều kiện thành công làm consumer cũ hành động sai.
- Thay đổi cấu trúc bắt buộc khiến client cũ không parse được.

Nếu chỉ thêm metadata tùy chọn và client cũ chấp nhận unknown fields, có thể giữ version hiện hữu theo chính sách tiến hóa đã thống nhất.

## 11. Hợp đồng sự kiện khi producer và consumer cùng tồn tại nhiều bản

Với event streaming, version cũ tồn tại không chỉ vì service chưa deploy, mà còn bởi **message lưu lại trong broker**.

Ví dụ event v1:

~~~json
{
  "eventId": "e-1001",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "orderId": "O-42",
  "amount": 390000
}
~~~

Event v2:

~~~json
{
  "eventId": "e-1001",
  "eventType": "OrderConfirmed",
  "schemaVersion": 2,
  "orderId": "O-42",
  "amount": 390000,
  "currency": "VND",
  "occurredAt": "2026-11-11T10:00:00Z"
}
~~~

Nếu amount ở cả hai bản đều có **cùng đơn vị và ý nghĩa**, event v2 thêm field có thể tương thích với v1 tùy schema và consumer. Nếu v2 đổi amount từ VND sang minor units của nhiều currency, cần contract mới hoặc chiến lược thích nghi chặt, không chỉ tăng schemaVersion và bỏ qua ý nghĩa.

### 11.1. Consumer mới phải chịu được event cũ

Nếu consumer v2 chỉ biết schemaVersion=2 và một batch v1 đang nằm trong queue, v2 có thể thất bại ngay khi deploy. Vì vậy thường triển khai consumer nhận cả v1 và v2 **trước** khi producer bắt đầu phát dạng mới.

~~~text
Time T0: producer v1 -> broker -> consumer v1
Time T1: producer v1 -> broker -> consumer v2 (reads v1)
Time T2: producer v2 -> broker -> consumer v2 (reads v1 + v2)
Time T3: old data expired / migrated / replay policy satisfied
Time T4: optionally remove v1 parsing
~~~

Đây là một trình tự phổ biến, không phải bắt buộc trong mọi topology. Phải kiểm tra đường phiên bản cũ của consumer trong T2 và producer cũ của các replica chưa cập nhật.

### 11.2. Envelope và nội dung sự kiện

Một event thường có phần metadata:

~~~json
{
  "eventId": "e-1001",
  "eventType": "OrderConfirmed",
  "schemaVersion": 2,
  "producer": "ordering",
  "occurredAt": "2026-11-11T10:00:00Z",
  "correlationId": "trace-abc",
  "payload": {
    "orderId": "O-42",
    "totalMinorUnits": 390000,
    "currency": "VND"
  }
}
~~~

Envelope giúp định tuyến, tracing và lựa chọn parser; nó không tự bảo đảm tương thích. Consumer vẫn cần hiểu rõ semantics, mapping phiên bản, thứ tự, idempotency và lỗi.

### 11.3. Đừng đổi ý nghĩa event cũ

Nếu OrderConfirmed v1 nghĩa “đã đặt thành công và có hàng giữ”, còn v2 nghĩa “chỉ tiếp nhận yêu cầu”, đừng giữ tên event mà thay ý nghĩa ngầm. Có thể dùng OrderAccepted hoặc OrderPlaced cho trạng thái PENDING và chỉ phát OrderConfirmed khi điều kiện cũ thực sự thỏa.

**Business event là một lời khẳng định về sự kiện đã xảy ra**, không phải một DTO có thể đổi nghĩa tùy ý.

### 11.4. Schema Registry và compatibility mode

Các nền tảng có thể cung cấp schema registry và kiểm tra compatibility. Một số chế độ thường gặp là backward, forward và full, có hoặc không có quy tắc xuyên nhiều phiên bản (transitive). Tên và mức bảo đảm phụ thuộc công cụ, serializer, định dạng schema và cấu hình.

Không nên hiểu “schema registry báo compatible” là hệ thống an toàn hoàn toàn: công cụ thường chỉ kiểm tra cấu trúc/schema theo quy tắc đã cấu hình, chứ không hiểu thay đổi giá trị enum, điều kiện business, rounding hay logic thanh toán. Cần contract tests và thử nghiệm message thật ở nhiều phiên bản.

### 11.5. Replay và retention thay đổi thời hạn hỗ trợ

Một consumer mới có thể replay event từ sáu tháng trước. Nếu chỉ lưu code parse v2 nhưng log còn v1, replay có thể lỗi. Cần một trong các chiến lược có kiểm soát:

- Duy trì parser/adapter đọc v1 theo cửa sổ replay.
- Chuẩn hóa dữ liệu qua migration/reprocessing có kiểm chứng.
- Version topic/event type khi thay đổi phá vỡ.
- Thiết kế snapshot/bootstrap và quy tắc retention phù hợp.

Không xóa hỗ trợ schema cũ chỉ vì dashboard hiện tại ghi “100% producer đã lên v2”.

## 12. Protobuf/gRPC: thêm field mà không phá wire contract

Với gRPC/Protocol Buffers, số field (tag) và wire type là phần quan trọng của hợp đồng. Ví dụ:

~~~proto
syntax = "proto3";

package pricing.v1;

message PriceQuote {
  string quote_id = 1;
  int64 total_minor_units = 2;
}
~~~

Muốn thêm currency:

~~~proto
syntax = "proto3";

package pricing.v1;

message PriceQuote {
  string quote_id = 1;
  int64 total_minor_units = 2;
  string currency = 3;
}
~~~

Bổ sung tag 3 thường cho phép consumer cũ bỏ qua unknown field theo cơ chế Protobuf, và consumer mới đọc message cũ với giá trị mặc định của currency. Nhưng **giá trị mặc định string rỗng không phải currency hợp lệ**. Consumer mới cần hiểu lúc nào dữ liệu cũ có thể thiếu và xử lý đúng nghiệp vụ.

### 12.1. Những điều không nên làm

- Không đổi tag 2 từ total_minor_units thành một field có ý nghĩa khác.
- Không dùng lại tag cũ sau khi xóa field.
- Không giả định mọi thay đổi type đều an toàn trên wire dù compiler có thể chấp nhận.
- Không thay đổi ý nghĩa enum mà chỉ giữ nguyên số/nhãn.
- Không coi giá trị mặc định của proto3 là dấu hiệu dữ liệu đã thực sự được gửi nếu contract cần phân biệt presence.

Ví dụ bảo lưu tag đã xóa:

~~~proto
syntax = "proto3";

message PriceQuote {
  string quote_id = 1;
  reserved 2;
  reserved "legacy_amount";
  string currency = 3;
}
~~~

Việc reserved ngăn tái sử dụng identifier bị xóa trong schema mới. Nếu cần phân biệt field có mặt hay không, có thể dùng optional hoặc wrapper/oneof phù hợp với phiên bản Protobuf và semantics. Contract phải chỉ rõ đường chuyển đổi từ dữ liệu cũ.

### 12.2. Streaming và rolling update

Trong các kết nối gRPC streaming kéo dài, client có thể giữ kết nối tới instance v1 trong khi deployment bắt đầu đưa instance v2 vào phục vụ request mới. Cần chính sách drain, deadline, reconnect, protocol negotiation và xử lý resume/cursor nếu stream có trạng thái. Không tự giả định stream đang mở sẽ chuyển tức thì sang v2.

## 13. Triển khai thứ tự nào cho an toàn?

Không có một thứ tự đúng cho mọi thay đổi, nhưng có quy tắc:

**Đưa khả năng đọc/hiểu mới vào bên nhận trước khi phía gửi bắt đầu phát dữ liệu mà bản nhận cũ không hiểu.** Đồng thời phải bảo đảm khi consumer mới xuất hiện trước, nó vẫn xử lý được dữ liệu cũ.

### 13.1. Khi thêm field response tùy chọn

Một đường triển khai khả thi:

1. Đảm bảo mọi client cũ chấp nhận field lạ hoặc server có thể trả schema cũ theo contract.
2. Deploy server mới vẫn trả field cũ và thêm field mới.
3. Deploy client mới có fallback khi chưa nhận field mới.
4. Kích hoạt tính năng mới sau khi biết server tương thích đã sẵn sàng.
5. Quan sát client và loại bỏ field cũ theo lịch đã thỏa thuận.

### 13.2. Khi thêm field request bắt buộc cho tính năng mới

Một đường triển khai khả thi:

1. Server mới hiểu field mới, nhưng client cũ vẫn gửi request cũ được.
2. Deploy server có khả năng xử lý field mới trên mọi instance liên quan.
3. Chỉ sau đó client mới bật gửi field và sử dụng semantics mới.
4. Với các server cũ ngoài kiểm soát, dùng capability negotiation hoặc version endpoint rõ.
5. Không cho một server cũ âm thầm bỏ qua yêu cầu bắt buộc của client mới.

### 13.3. Khi đổi event schema

Một đường triển khai khả thi:

1. Deploy consumer mới đọc được event cũ và mới.
2. Đảm bảo producer cũ vẫn có thể phát v1 trong rolling window.
3. Deploy producer mới phát phiên bản mới theo contract.
4. Quan sát lag, parse errors, DLQ và business outcome.
5. Đợi đủ thời gian retention/replay và trạng thái rollout trước khi xóa parser v1.

### 13.4. Khi đổi database schema

Một đường triển khai khả thi:

1. Expand schema không làm v1 lỗi.
2. Deploy code đọc/ghi theo chính sách chuyển tiếp.
3. Backfill/kiểm chứng dữ liệu khi cần.
4. Đổi đường đọc/ghi mới có kiểm soát.
5. Xóa schema cũ ở một release sau, khi rollback và các background job cũ không còn cần.

## 14. Rolling, canary, blue/green: phiên bản vẫn có thể gặp nhau

### 14.1. Rolling update

Các instance được thay lần lượt. Trong một khoảng thời gian, load balancer có thể gửi request tới server cũ hoặc mới. Contract phải an toàn cho phiên bản upstream/downstream tương ứng; health check thành công chưa chứng minh semantic compatibility.

### 14.2. Canary release

Một tỷ lệ nhỏ traffic đi vào bản mới để đo lỗi và kết quả. Canary chỉ an toàn khi:

- Request mới không ghi dữ liệu khiến bản cũ không thể đọc.
- Event mới không phá consumer cũ đang chạy.
- Rollback không làm dữ liệu do bản mới sinh trở nên vô nghĩa với bản cũ.
- Metrics phân biệt canary và baseline, kể cả business errors.

Canary giúp giảm phạm vi ảnh hưởng, **không chữa được contract phá vỡ**. Dữ liệu v2 đã ghi có thể ảnh hưởng user hoặc consumer không đi qua canary nếu chúng dùng chung database/topic.

### 14.3. Blue/green deployment

Có hai môi trường đang sẵn sàng. Chuyển traffic từ blue sang green có thể nhanh, nhưng shared database, queue và client cũ vẫn tồn tại. Nếu green ghi schema mà blue không đọc được, rollback sang blue vẫn lỗi.

### 14.4. Feature flags và capability

Feature flag tách việc triển khai code mới khỏi **kích hoạt hành vi mới**. Có thể deploy producer có khả năng phát event v2 nhưng giữ phát v1 cho đến khi các consumer sẵn sàng.

Tuy nhiên flag không thay thế migration, có thể tạo nhiều nhánh code khó quản lý và không phải cơ chế bảo mật. Khi bật/tắt cần chính sách giữ trạng thái dữ liệu và khả năng phục hồi. Với hệ thống đối tác, capability negotiation có thể cho phép consumer/client xác nhận rõ server có hỗ trợ chức năng mới thay vì đoán qua số phiên bản.

## 15. Rollback phải tính cả data compatibility

Một rollback code thành công không đảm bảo rollback hệ thống.

Ví dụ:
- Pricing v2 tạo quote có currency="USD".
- Pricing v1 chỉ hỗ trợ VND và không biết dữ liệu USD.
- Hạ code về v1 nhưng database đã chứa quote USD.

Dù service có thể khởi động, thao tác đọc/xử lý quote cũ có thể sai. Vì vậy:

1. Xác định **new data written by v2** có thể được v1 đọc hay không.
2. Cần lớp tương thích hai chiều hoặc giới hạn hành vi mới cho đến khi không cần rollback.
3. Có phương án roll-forward nếu không thể đảo migration an toàn.
4. Với migration không đảo ngược, phải có kế hoạch sao lưu/khôi phục hoặc quy trình chuyển tiếp nghiệp vụ cụ thể.
5. Không dùng rollback tự động cho những thay đổi có side effect mà code cũ không hiểu.

### 15.1. Rollback và event mới

Nếu producer v2 đã phát OrderConfirmed schema v2, đưa consumer về v1 có thể làm consumer đọc event tồn đọng mà nó không hiểu. Khi lên kế hoạch rollback, cần giữ schema/event tương thích trong cửa sổ hoặc có cách vô hiệu hóa phát dữ liệu mới khi hạ phiên bản, với xử lý message đã phát.

### 15.2. Rollback không được làm trùng tác vụ

Các lệnh PaymentCaptured, ReserveStock hoặc RefundInitiated có thể đã được xử lý bởi phiên bản mới. Rollback không được resend command với id mới và gây thực hiện hai lần. Idempotency, event ID và transaction history phải giữ được qua nhiều phiên bản.

## 16. Kiểm thử hợp đồng khi có nhiều phiên bản

Unit test của bản v2 với bản v2 là chưa đủ. Cần kiểm thử các cặp phiên bản có thể gặp thực tế.

### 16.1. Ma trận contract tests

| Kịch bản | Producer | Consumer | Điều cần xác nhận |
| --- | --- | --- | --- |
| Legacy | P1 | C1 | Chức năng hiện tại không đổi |
| Old data, new reader | P1 | C2 | Fallback/default có ngữ nghĩa đúng |
| New data, old reader | P2 | C1 | Unknown field hoặc dual-format không phá |
| New data, new reader | P2 | C2 | Tính năng mới hoạt động đúng |
| Rollback | P2 data | C1 after rollback | Đọc/tránh xử lý sai dữ liệu mới |
| Event replay | P1 event history | C2 | Consumer mới phục hồi dữ liệu cũ |
| Delayed message | P1 and P2 interleaved | C2 | Version/order/idempotency được xử lý |

Không phải mọi tổ hợp có thể xảy ra trong một topology. Hãy ghi rõ **giả định ngăn những cặp còn lại gặp nhau**, thay vì bỏ test vì tin rollout sẽ diễn ra “ngay lập tức”.

### 16.2. Consumer-driven contract testing

Một consumer có thể mô tả chính xác những field/status/error mà nó thật sự sử dụng; provider xác nhận vẫn đáp ứng những kỳ vọng đó. Các công cụ như Pact hoặc Spring Cloud Contract có thể hỗ trợ workflow contract testing, tùy hệ sinh thái.

Điểm chính không phải chọn một tên công cụ mà là quy trình:

- Consumer công bố kỳ vọng trên từng contract phiên bản.
- Provider chạy kiểm thử chống breaking change trước khi deploy.
- Pipeline biết consumer nào còn đang chạy thực tế.
- Không release provider có thay đổi phá consumer chưa được chuyển.
- Với event, kiểm tra cả producer schema và khả năng đọc message thực của consumer.

### 16.3. Golden payloads và trường hợp có nghĩa nghiệp vụ

Lưu các payload mẫu của phiên bản cũ/mới và kiểm thử kết quả giải mã, hành vi và business validation:

- JSON thiếu field mới.
- JSON có unknown optional field.
- JSON có enum value không biết trước.
- Timestamp khác timezone/precision.
- Amount lớn, giá trị 0, currency khác.
- Event trùng ID, đến muộn, out-of-order.
- Message có schemaVersion cũ nhưng vẫn được replay.
- Lỗi 404/409/422/503 theo contract.
- Dữ liệu v2 mà v1 sẽ gặp sau rollback.

Schema validator có thể báo pass trong khi ý nghĩa một enum đổi sai. Vì vậy test business semantics là bắt buộc với thay đổi quan trọng.

## 17. Versioning và idempotency xuyên quá trình triển khai

Trong các luồng command, retry và deploy cùng lúc có thể khiến một lệnh được xử lý bởi nhiều bản code.

Ví dụ, client gọi Payment v1, bị timeout, sau đó retry khi load balancer đã chuyển sang Payment v2. Nếu cả hai cùng sử dụng idempotency key ổn định và một nơi kiểm soát kết quả đã xử lý, hệ thống có thể trả về cùng kết quả hoặc trạng thái đã ghi.

Nếu v2 thay cách tạo idempotency key, hai bản có thể không nhận diện cùng một ý định giao dịch. Một thay đổi “không phá JSON schema” vẫn phá **tính đúng một lần về mặt nghiệp vụ**.

### 17.1. Định nghĩa ID ổn định

- eventId cần ổn định khi phát lại cùng một event.
- commandId/requestId cần giữ nguyên khi retry cùng ý định.
- paymentId/reservationId cần ánh xạ được giữa các phiên bản.
- Deduplication store cần có quyền sở hữu và thời hạn lưu phù hợp.
- Versioning không được tạo một ý nghĩa mới cho cùng khóa định danh mà không có migration.

### 17.2. Một lần xử lý về mặt nghiệp vụ không đến từ broker

Một số broker hỗ trợ cơ chế được gọi là exactly-once trong phạm vi nhất định. Nhưng email, payment gateway, database ngoài transaction của broker hoặc service khác không tự được bao phủ. Consumer vẫn cần idempotency và reconciliation.

Với một event đang chuyển từ v1 sang v2, có thể xuất hiện **hai biểu diễn của cùng một sự kiện**. Nếu quyết định dual publish, phải có cơ chế để consumer không tính doanh thu hay gửi email hai lần, ví dụ cùng business event ID và logic lọc theo contract được thiết kế cụ thể.

## 18. Dual publish và dual read: khi cần và khi không

Có lúc để chuyển consumer không thể nâng cấp đồng loạt, producer phải phát hai event type hoặc hai topic.

~~~text
Order Service
   |-- OrderConfirmedV1 --> old consumers
   +-- OrderConfirmedV2 --> new consumers
~~~

Cách này có thể hữu ích trong giai đoạn chuyển đổi nhưng làm tăng độ phức tạp:

- Hai message là hai hình thức của cùng một business fact hay hai event khác nhau?
- Một consumer có thể subscribe cả hai và đếm trùng không?
- Nếu publish v1 thành công nhưng v2 thất bại, quy trình đối soát là gì?
- Có thể duy trì hai schema trong thời gian bao lâu?
- Khi nào được xóa luồng cũ, và bằng chứng là gì?

Tốt nhất ưu tiên **thay đổi additive tương thích** trong cùng event type nếu semantics cho phép. Dual publish chỉ nên dùng khi contract thật sự khác hoặc consumer không thể đổi theo một đường chung.

**Dual read** cũng cần quy tắc rõ khi có nguồn cũ và mới: nguồn nào có thẩm quyền, nếu hai nơi khác nhau thì ưu tiên và cảnh báo như thế nào, lúc nào ngừng fallback? Không nên tạo hai nguồn sự thật bình đẳng trong thời gian dài.

## 19. Mức độ tương thích theo ý nghĩa nghiệp vụ

Có những thay đổi nhìn rất nhỏ về code nhưng lớn với hành vi.

### 19.1. Enum mới

~~~json
{"paymentStatus":"PENDING_REVIEW"}
~~~

Consumer cũ chỉ biết PAID/FAILED và một nhánh else mặc định là FAILED. Khi producer mới thêm PENDING_REVIEW, consumer cũ có thể hủy đơn hoặc hoàn tiền sai.

Giải pháp: định nghĩa UNKNOWN/UNRECOGNIZED khi phù hợp và **chính sách an toàn**. Với payment status, unknown không có nghĩa failed. Có thể yêu cầu người tiêu thụ dừng quyết định, tra lại nguồn chuẩn hoặc chuyển sang trạng thái chờ.

### 19.2. Field mới mang điều kiện quan trọng

Thêm requiresApproval=true vào response có vẻ additive. Nhưng nếu consumer cũ bỏ qua rồi vẫn hoàn tất tác vụ, hệ thống có thể vi phạm chính sách. Khi field mới làm thay đổi luật quyết định, cần versioning hoặc capability gate phù hợp, không chỉ tin unknown-fields compatibility.

### 19.3. Thay đổi validation

Server v2 yêu cầu postalCode bắt buộc với mọi order trong khi client v1 không gửi. Đây là breaking change ở request. Có thể cần giữ đường v1 với quy tắc cũ cho trường hợp hợp lệ, hoặc cung cấp migration/default có ngữ nghĩa chính xác. Không nới validation nếu điều đó vi phạm quy định hoặc tính đúng đắn.

### 19.4. Thay đổi default

V1 hiểu trường omitted là false; v2 hiểu omitted là true. Parser không lỗi, nhưng hành vi thay đổi. Đặt default rõ, test request cũ và chỉ đổi semantics qua contract/version mới nếu cần.

### 19.5. Sửa lỗi cũng có thể phá contract

Đôi khi consumer vô tình phụ thuộc một bug của provider. Sửa bug là đúng nhưng vẫn có thể ảnh hưởng production. Cần phát hiện qua contract tests và thỏa thuận chuyển đổi; tránh hy sinh yêu cầu nghiệp vụ quan trọng chỉ để giữ một bug vô hạn.

## 20. Kiểm soát migration bằng dữ liệu production

Cần quan sát những chỉ số đủ trả lời “còn ai sử dụng bản cũ?”:

| Chỉ số | Ý nghĩa | Hạn chế cần hiểu |
| --- | --- | --- |
| Request theo API version | Ai đang gọi /v1, /v2 | Có thể có client không hoạt động trong cửa sổ đo |
| User agent / client version | Tỷ lệ mobile/SDK cũ | Có thể không chính xác hoặc bị thiếu |
| Consumer group lag | Message còn tồn và mức chậm xử lý | Lag bằng 0 không chứng minh replay quá khứ không xảy ra |
| Event schema version | Bản dữ liệu hiện được phát và tiêu thụ | Message cũ còn trong retention hoặc backup |
| Parse/validation errors | Phiên bản mới có hiểu hợp đồng không | Không đo được mọi lỗi ngữ nghĩa nghiệp vụ |
| Contract test matrix | Cặp phiên bản dự kiến có tương thích không | Chỉ bao phủ kịch bản đã kiểm thử |
| Rollback compatibility | Bản cũ có đọc dữ liệu mới không | Có thể cần thử riêng với snapshot production |
| Deprecated field usage | Consumer còn đọc field cũ không | Không phải lúc nào đo được từ phía server |
| Feature flag state | Hành vi mới đang bật cho ai | Flag có thể lệch giữa instance/region |

Tránh xóa hợp đồng cũ chỉ vì một biểu đồ “0 requests v1 hôm nay”. Một đối tác có thể chạy batch hàng tháng; một app di động có thể mở lại sau vài tuần; một consumer có thể replay message cũ bất kỳ lúc nào trong retention.

### 20.1. Chốt tiêu chí ngừng hỗ trợ

Một kế hoạch có thể nêu:

- Thời hạn thông báo và hỗ trợ khách hàng/đối tác.
- Khoảng quan sát đủ dài theo tần suất dùng thực tế.
- Tất cả consumer quan trọng đã xác nhận chuyển.
- Broker retention, replay, DLQ và backup đã được xử lý.
- Không còn rollback target yêu cầu schema cũ.
- Test dữ liệu và contract cuối cùng thành công.
- Có khả năng rollback thay đổi **xóa field** hoặc kế hoạch roll-forward an toàn.

## 21. Playbook triển khai an toàn cho một thay đổi contract

### Trước release

1. Viết rõ contract cũ, contract mới, ý nghĩa thay đổi.
2. Xác định producer/consumer, API caller, message subscriber, batch jobs và client ngoại vi.
3. Vẽ **ma trận phiên bản** các cặp có thể gặp nhau.
4. Tạo contract tests và dữ liệu mẫu theo các cặp đó.
5. Xác định cần expand schema/API, capability negotiation hay major version.
6. Thiết kế cách tắt feature/rollback với dữ liệu đã ghi.
7. Thống nhất SLO, error budget, chỉ số giám sát và owner.

### Trong release

1. Deploy khả năng đọc tương thích khi phù hợp.
2. Expand dữ liệu/hợp đồng mà không xóa trường cũ.
3. Rollout producer/server mới qua canary hoặc rolling update.
4. Kích hoạt tính năng mới khi tất cả dependency cần thiết đã sẵn sàng.
5. Quan sát error, schema version, latency, consumer lag và business outcome.
6. Tạm dừng rollout nếu một cặp phiên bản có hành vi sai.

### Sau release

1. Kiểm tra toàn bộ consumer đã chuyển và queue/event retention phù hợp.
2. Backfill và reconciliation dữ liệu còn thiếu.
3. Gửi thông báo deprecation khi có client/đối tác ngoài tổ chức.
4. Chờ cửa sổ hỗ trợ kết thúc; test khả năng ngừng trường cũ.
5. Xóa contract cũ ở release riêng và theo dõi tiếp.

Không dùng một lần triển khai lớn gồm đổi schema, đổi API, đổi event và xóa field cũ cùng lúc nếu không có bảo đảm kiểm chứng được rằng các trạng thái trung gian an toàn.

## 22. Những lỗi kiến trúc thường gặp

**“Cả hai service sẽ deploy cùng lúc.”**  
Trong microservices, deploy thường không nguyên tử. Load balancer, retry, long-lived connection và rollback tạo cửa sổ phiên bản hỗn hợp. Cần khả năng tương thích, không dựa vào đồng hồ chung.

**“Chỉ cần thêm /v2 là xong.”**  
Version route chỉ là tên. Vẫn cần migration data, logic thích nghi, kiểm thử, rollback và deprecation.

**“JSON thêm field luôn an toàn.”**  
Strict client, semantics mới hoặc field bắt buộc về nghiệp vụ có thể phá hệ thống.

**“Schema registry báo compatible thì chắc chắn không lỗi.”**  
Registry không hiểu quy tắc thanh toán, đổi meaning enum hoặc business default.

**“Triển khai producer trước luôn đúng.”**  
Nếu consumer cũ không hiểu payload mới, producer trước gây lỗi. Thứ tự phải xét **hướng dữ liệu** và cặp phiên bản thật.

**“Đã nâng producer xong thì xóa parser event cũ.”**  
Consumer có thể gặp event cũ trong queue, replay, DLQ hoặc backup.

**“Rollback code là hoàn tác toàn hệ thống.”**  
Database và event đã được phiên bản mới ghi có thể không tương thích code cũ.

**“Unknown status cứ coi là FAILED.”**  
Với payment, order hoặc fulfillment, trạng thái unknown cần chính sách an toàn; suy luận failed có thể gây tác vụ trùng.

**“Dual publish làm tăng độ tin cậy mà không tốn gì.”**  
Hai payload cho một business event có thể tạo duplication, drift và chi phí reconciliation.

**“Mọi thay đổi phải tăng major version.”**  
Version mới cho mọi field tùy chọn làm tăng số contract phải quản lý; nên phân biệt thay đổi compatible và incompatible.

## 23. Tình huống thực hành

### Bài 1 — Rolling update REST

Order Service v1 gọi Pricing. Pricing v2 thêm currency vào JSON response. Consumer v1 dùng parser bỏ qua unknown field; consumer v2 yêu cầu currency. Khi Pricing v1 và v2 cùng chạy, chuyện gì xảy ra?

**Gợi ý lời giải:** Consumer v1 có thể đọc response v2 nếu mọi field cũ giữ semantics; consumer v2 sẽ gặp response v1 thiếu currency. Cần fallback đúng nghiệp vụ, capability check hoặc chờ Pricing v2 triển khai hết trước khi bật tính năng yêu cầu currency. Không đoán currency nếu không có cơ sở.

### Bài 2 — Validation mới trên request

Client v2 gửi requiresManualReview=true; server v1 bỏ qua field và trả 200. Có an toàn không?

**Gợi ý lời giải:** Không nếu điều kiện review là bắt buộc. Phải triển khai server hiểu semantics trước hoặc dùng endpoint/capability mới để tránh server cũ silently ignore request quan trọng.

### Bài 3 — Message trong queue

OrderConfirmed v1 không có occurredAt. Consumer v2 chỉ parse v2, trong queue còn 5.000 message v1. Có thể deploy consumer v2 ngay không?

**Gợi ý lời giải:** Không nếu consumer không đọc được v1. Cần adapter/fallback, backfill/migration sự kiện có kiểm soát, hoặc tách luồng theo version rồi xử lý backlog. Không xóa parser v1 khi còn dữ liệu v1.

### Bài 4 — Đổi enum thanh toán

Producer bổ sung status PENDING_REVIEW; consumer cũ map unknown sang FAILED. Đổi schemaVersion thành 2 có đủ an toàn không?

**Gợi ý lời giải:** Không. Contract semantic bị phá; cần bảo vệ consumer cũ, chọn đường versioned/capability, đổi consumer theo safe handling trước rồi mới phát trạng thái mới.

### Bài 5 — Rename cột database

Một đội dùng migration RENAME COLUMN trong khi một nửa pod vẫn đọc tên cũ. Biểu hiện và hướng giải quyết?

**Gợi ý lời giải:** Pod cũ lỗi truy vấn. Dùng expand thêm cột mới, chuyển/bổ sung dữ liệu an toàn, deploy code đọc hai dạng, backfill, chuyển reader, rồi drop cột cũ khi không còn pod/job/rollback cần nó.

### Bài 6 — Rollback sau canary

Pricing v2 phát quote USD vào cùng database. Hạ về v1 chỉ biết VND. Có thể tự động rollback không?

**Gợi ý lời giải:** Chưa chắc. Cần xem v1 có thể đọc/không xử lý sai quote USD, có adapter tương thích hoặc flag giới hạn ghi data mới trước không. Nếu migration không đảo được thì dùng roll-forward hoặc kế hoạch recovery riêng.

### Bài 7 — Protobuf field reuse

Một field Protobuf tag 4 bị xóa; người phát triển tái sử dụng tag 4 cho currency. Hợp đồng có nguy cơ gì?

**Gợi ý lời giải:** Dữ liệu cũ có tag 4 với ý nghĩa khác có thể bị đọc sai hoặc gây lỗi wire/semantic. Không tái sử dụng tag; đánh dấu reserved field number/name và thêm tag mới.

### Bài 8 — Bản mobile cũ

Web client đã lên v2 nhưng ứng dụng mobile cũ vẫn hoạt động hàng tháng. Có thể xóa /v1 sau một tuần không có request từ web không?

**Gợi ý lời giải:** Không thể kết luận từ traffic web. Cần inventory phiên bản mobile, thời gian hỗ trợ, dữ liệu request thực từ các kênh, lịch thông báo và cách xử lý client cũ chưa cập nhật.

### Bài 9 — Cùng một event phát hai lần ở hai schema

Trong giai đoạn dual publish, Analytics nhận OrderConfirmedV1 và OrderConfirmedV2 của cùng order nên cộng doanh thu hai lần. Cách ngăn?

**Gợi ý lời giải:** Xác định cùng business event ID, subscription và logic dedup/schema migration; nếu dual publish, consumer không được tự coi chúng là hai giao dịch độc lập. Cần đối soát để sửa projection đã tính trùng.

### Bài 10 — Định nghĩa “compatible”

Một kỹ sư nói “thêm enum value là backward compatible vì JSON parse được”. Bạn cần hỏi gì?

**Gợi ý lời giải:** Consumer cũ xử lý unknown enum thế nào? Có thể ra quyết định sai không? Giá trị mới sẽ xuất hiện trước khi consumer được nâng cấp không? Có contract tests và rollout gate? Compatibility phải bao gồm semantics và hành vi.

## 24. Mẫu hồ sơ thay đổi hợp đồng

~~~text
Contract name: OrderConfirmed
Current schema/version: v1
Proposed schema/version: v2
Producer: Ordering
Consumers: Notification, Analytics, Fulfillment, Support
Change: thêm occurredAt và currency
Semantic change: không / có; mô tả rõ nếu có
Data direction: Ordering -> event consumers
Compatibility window: [theo retention và lịch triển khai thực tế]
Version matrix: P1/C1, P1/C2, P2/C1, P2/C2
Old message handling: C2 reads v1 with explicit fallback
Rollout order: C2 capable readers -> P2 -> observe -> deprecate v1
Feature flags: [đường phát v2, nếu cần]
Rollback condition: [P2 data readable by C1?]
Tests: schema compatibility, contract tests, replay, canary
Metrics: event versions, parse errors, lag, DLQ, business outcomes
Deprecation owner: [nhóm sở hữu hợp đồng]
Removal criteria: no active consumers + retention/replay/rollback addressed
~~~

Mẫu này giúp buộc đội ngũ nêu rõ **cặp phiên bản** và **chứng cứ dừng hỗ trợ**, thay vì thảo luận chung chung “có version rồi”.

## 25. Checklist trước khi triển khai nhiều phiên bản

- [ ] Đã xác định producer/consumer và chiều dữ liệu cho từng request, response, command, event.
- [ ] Đã liệt kê những phiên bản có thể đồng thời tồn tại trên pod, worker, mobile, đối tác.
- [ ] Có ma trận cặp phiên bản và tests tương ứng.
- [ ] Thay đổi additive có giữ nguyên meaning của field, status và errors cũ không?
- [ ] Consumer mới có thể đọc dữ liệu từ producer cũ không?
- [ ] Consumer cũ có thể đọc dữ liệu producer mới trong cửa sổ rollout không?
- [ ] Field mới có phải chỉ optional về schema hay còn là yêu cầu bắt buộc nghiệp vụ?
- [ ] Nếu parser bỏ qua unknown field, lệnh có thể thành công sai semantics không?
- [ ] Có expand–migrate–contract cho API/database/event khi cần?
- [ ] Có backfill/migration dữ liệu an toàn và một nguồn sự thật rõ?
- [ ] Đã xét broker retention, queue backlog, DLQ và replay chưa?
- [ ] Có kế hoạch rollback với dữ liệu mới đã ghi và message mới đã phát chưa?
- [ ] Idempotency key, eventId và contract identity ổn định qua các phiên bản không?
- [ ] Có metrics theo contract version và business outcome trong canary/rolling không?
- [ ] Có lịch deprecation, thông báo client/đối tác và chứng cứ kết thúc hỗ trợ không?
- [ ] Chỉ xóa field/endpoint/column cũ trong release riêng sau khi đủ bằng chứng?

## 26. Ghi nhớ

1. **Nhiều phiên bản cùng tồn tại là bình thường.** Rolling update, canary, retry, mobile client, worker cũ và message replay làm “deploy đồng thời” không đáng tin cậy.
2. **Tương thích phải được định nghĩa theo hướng và cặp phiên bản.** Producer mới/consumer cũ và producer cũ/consumer mới có rủi ro khác nhau.
3. **Schema compatible chưa chắc semantic compatible.** Giữ tên field nhưng đổi ý nghĩa có thể gây lỗi nghiệp vụ nghiêm trọng.
4. **Expand → Migrate → Contract** cho phép triển khai từng bước, hỗ trợ rollback rồi mới xóa hợp đồng cũ.
5. **Kiểm tra cả request và response.** Server cũ âm thầm bỏ qua field bắt buộc trong command có thể nguy hiểm hơn trả lỗi parse.
6. **Event versioning phải xét backlog, retention và replay.** Producer mới hoàn tất rollout không có nghĩa event cũ biến mất.
7. **Rollback phải đi cùng data compatibility.** Bản code cũ cần đọc được dữ liệu mới hoặc có kế hoạch phục hồi phù hợp.
8. **Contract tests, canary metrics và theo dõi consumer thực tế** là cơ sở xác nhận có thể ngừng hỗ trợ phiên bản cũ.
9. **Chọn version mới khi thật sự có thay đổi phá vỡ.** Với thay đổi additive có semantics ổn định, giữ contract tương thích thường giảm chi phí.
10. **Quyền sở hữu nghiệp vụ và dữ liệu không đổi khi nâng phiên bản.** Tương thích triển khai là công cụ để các context phát hành độc lập mà không làm sai hành vi của nhau.