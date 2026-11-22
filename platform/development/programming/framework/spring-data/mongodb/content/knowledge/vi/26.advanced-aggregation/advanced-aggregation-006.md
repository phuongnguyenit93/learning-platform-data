# Biểu thức ngày giờ, múi giờ và nhóm theo thời gian

## 1. Bài toán: “doanh thu ngày 1/6” thuộc múi giờ nào?

Một hệ thống bán hàng lưu thời điểm thanh toán của từng đơn hàng và cần làm báo cáo doanh thu theo **ngày, giờ, tuần và tháng**. Ví dụ, người quản trị cửa hàng ở Việt Nam muốn xem các đơn được thanh toán trong ngày **01/06/2025 theo giờ Việt Nam**.

Hai sự kiện sau đều xảy ra gần ranh giới ngày:

~~~text
2025-05-31T16:59:00Z -> 2025-05-31 23:59 tại Asia/Ho_Chi_Minh
2025-05-31T17:01:00Z -> 2025-06-01 00:01 tại Asia/Ho_Chi_Minh
~~~

Nếu nhóm theo **ngày UTC**, hai sự kiện thuộc cùng ngày 31/5. Nếu nhóm theo **ngày ở Việt Nam**, chúng thuộc hai ngày khác nhau. Cả hai kết quả có thể đúng về mặt kỹ thuật, nhưng chỉ một kết quả đáp ứng câu hỏi của người dùng.

Đó là lý do biểu thức ngày giờ trong MongoDB không chỉ là chuyển Instant thành chuỗi. Cần thống nhất:

- Sự kiện được lưu dưới kiểu nào?
- Múi giờ nào định nghĩa ngày kinh doanh?
- Truy vấn lọc khoảng thời gian theo UTC hay theo lịch địa phương?
- Nhóm theo ngày/tuần/tháng có dựa trên cùng múi giờ?
- Hệ thống có thay đổi giờ mùa hè (*daylight saving time*, DST) không?
- Làm sao biểu diễn một bucket thời gian để không nhầm khi sort hoặc hiển thị?

Bài **Biểu thức ngày giờ, múi giờ và nhóm theo thời gian** thuộc chương **Aggregation nâng cao** của module **SPRING_DATA_MONGODB**. Module tập trung kết nối và ánh xạ document, thao tác qua MongoTemplate hoặc repository, thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu. Nội dung này hướng đến một pipeline aggregation có kết quả đúng cả về nghiệp vụ lẫn ranh giới thời gian.

Sau bài, bạn có thể:

1. Phân biệt BSON Date, UTC instant, ngày lịch địa phương và múi giờ.
2. Dùng **$dateTrunc**, **$dateToString**, **$dateFromString** và các date operators liên quan.
3. Nhóm theo giờ/ngày/tuần/tháng với timezone phù hợp.
4. Đặt **$match** theo khoảng UTC được tính từ lịch địa phương để tận dụng index.
5. Xử lý DST, tuần ISO, năm chuyển giao, timestamp lỗi và dữ liệu thiếu.
6. Viết aggregation với **MongoTemplate** và **ReactiveMongoTemplate**.
7. Kiểm thử ranh giới ngày, hiệu năng và tính nhất quán của các phép tính.

## 2. Mô hình dữ liệu: đơn hàng đã thanh toán

Giả sử collection **orders** có các document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  status: "PAID",
  createdAt: ISODate("2025-05-31T16:59:00Z"),
  totalMinor: NumberLong("100000")
}
~~~

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tenantId: "shop-a",
  status: "PAID",
  createdAt: ISODate("2025-05-31T17:01:00Z"),
  totalMinor: NumberLong("200000")
}
~~~

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439013"),
  tenantId: "shop-a",
  status: "PAID",
  createdAt: ISODate("2025-06-01T01:00:00Z"),
  totalMinor: NumberLong("150000")
}
~~~

Trong ví dụ, **createdAt** là BSON Date; dữ liệu tiền lưu theo đơn vị nhỏ nhất để tránh các lỗi số thực dấu phẩy động khi cộng tiền. Với hệ thống thật, cần chọn thời điểm chính xác cho metric: doanh thu theo ngày thanh toán thường nên dựa vào **paidAt** thay vì createdAt. Ở đây sử dụng createdAt để minh họa và giả định chỉ lọc status=PAID.

Entity Java:

~~~java
package com.example.orders;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id ObjectId id,
    String tenantId,
    String status,
    Instant createdAt,
    long totalMinor
) {}
~~~

**Instant** biểu diễn một thời điểm trên trục thời gian; không chứa tên múi giờ của người dùng. **@Document** giúp Spring Data ánh xạ entity tới collection. Tên field được dùng trong các pipeline BSON của bài trùng với tên đã lưu.

### 2.1. Một bộ dữ liệu, hai cách nhóm

| Thời điểm UTC | Ngày ở UTC | Ngày tại Asia/Ho_Chi_Minh |
| --- | --- | --- |
| 2025-05-31T16:59Z | 31/05 | 31/05 |
| 2025-05-31T17:01Z | 31/05 | 01/06 |
| 2025-06-01T01:00Z | 01/06 | 01/06 |

Nếu báo cáo ngày 01/06 theo giờ Việt Nam, kết quả cho ba document trên là **2 đơn** và **350.000 đơn vị tiền nhỏ nhất**. Nếu nhóm theo ngày UTC, kết quả sẽ khác.

## 3. BSON Date, Instant, LocalDate và ZonedDateTime

Một nguồn lỗi phổ biến là đánh đồng mọi giá trị “có ngày giờ” thành cùng một kiểu.

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| BSON Date | ISODate("2025-05-31T17:01:00Z") | Thời điểm, lưu dưới dạng số mili giây tính từ Unix epoch. |
| Java Instant | 2025-05-31T17:01:00Z | Một thời điểm tuyệt đối; không mang quy tắc múi giờ lịch. |
| LocalDate | 2025-06-01 | Một ngày lịch, chưa xác định ranh giới UTC nếu chưa có timezone. |
| LocalDateTime | 2025-06-01T00:01 | Thời gian “trên đồng hồ”, thiếu timezone/offset. |
| ZoneId | Asia/Ho_Chi_Minh | Tên vùng có quy tắc chuyển đổi lịch theo thời điểm. |
| ZonedDateTime | 2025-06-01T00:01+07:00[Asia/Ho_Chi_Minh] | Đồng hồ địa phương kèm vùng và offset tương ứng. |
| OffsetDateTime | 2025-06-01T00:01+07:00 | Đồng hồ địa phương kèm offset, nhưng không nhất thiết biết tên vùng. |

**BSON Date không lưu tên timezone.** Một thời điểm có thể được hiển thị dưới nhiều múi giờ, nhưng giá trị instant cơ bản vẫn giống nhau.

~~~java
import java.time.Instant;
import java.time.ZoneId;

Instant moment = Instant.parse("2025-05-31T17:01:00Z");

var inVietnam = moment.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
var inNewYork = moment.atZone(ZoneId.of("America/New_York"));
~~~

Hai biến biểu diễn cùng **moment**, nhưng phần giờ/ngày địa phương có thể khác. Đó chính là lý do cần truyền timezone khi nhóm dữ liệu theo lịch kinh doanh.

### 3.1. Không lưu thời điểm dưới dạng chuỗi nếu có thể tránh

Không nên dùng field như:

~~~javascript
{ createdAt: "01/06/2025 00:01" }
~~~

Chuỗi trên không cho biết timezone, định dạng phụ thuộc ngôn ngữ và thường không phù hợp để sort/range query theo thời điểm. Nếu dữ liệu nguồn có chuỗi thời gian, nên chuẩn hóa thành BSON Date khi nhập và lưu thông tin timezone nguồn khi nghiệp vụ cần.

### 3.2. Độ chính xác của thời gian

BSON Date có độ chính xác **mili giây**. Java Instant có thể giữ phần nhỏ tới nano giây nhưng khi chuyển sang BSON Date thường phải theo độ chính xác của kiểu lưu. Không xây logic phân nhóm dựa trên phần nano giây rồi giả định MongoDB bảo toàn nó trong Date.

## 4. Múi giờ IANA khác offset cố định

MongoDB date operators có thể nhận tham số **timezone**. Nên ưu tiên tên vùng theo cơ sở dữ liệu múi giờ IANA:

~~~text
Asia/Ho_Chi_Minh
America/New_York
Europe/Berlin
Asia/Tokyo
~~~

Một offset như **+07:00** cũng có thể biểu diễn chênh lệch với UTC, nhưng **offset không chứa quy tắc đổi giờ theo mùa hoặc lịch sử**.

Ví dụ:

- Asia/Ho_Chi_Minh hiện sử dụng UTC+07:00 và không thực hiện DST hiện nay.
- America/New_York có các thời điểm dùng UTC−05:00 và UTC−04:00.
- Cùng một vùng có thể thay đổi offset theo năm, theo chính sách lịch sử hoặc thay đổi pháp luật.

**Không thay America/New_York bằng "-05:00" cho cả năm** nếu muốn báo cáo đúng thời gian địa phương.

### 4.1. Tách timezone của dữ liệu và timezone báo cáo

Một đơn hàng có thể được tạo từ khách tại múi giờ khác, nhưng chủ cửa hàng muốn báo cáo theo **timezone của cửa hàng**. Hãy quy định rõ:

- Timezone theo tenant/cửa hàng.
- Timezone theo người xem.
- Timezone UTC thống nhất cho toàn công ty.

Nếu mỗi người xem tự đổi timezone, cùng một đơn hàng có thể nằm ở các ngày báo cáo khác nhau. Đây là hành vi hợp lý khi kỳ vọng rõ ràng, không phải lỗi MongoDB.

### 4.2. Kiểm soát timezone input

Nếu client gửi timezone:

1. Kiểm tra giá trị là timezone hợp lệ.
2. Ràng buộc vào timezone được nghiệp vụ cho phép.
3. Giới hạn cách thay đổi timezone của các báo cáo đã chốt.
4. Ghi lại timezone đã dùng trong metadata kết quả.

Không ghép một chuỗi timezone không tin cậy trực tiếp thành JSON pipeline bằng thao tác nối chuỗi; tạo BSON bằng API Document hoặc expression builders, và validate đầu vào.

## 5. $dateTrunc: gom thời điểm vào bucket lịch

**$dateTrunc** đưa một thời điểm về đầu khoảng thời gian theo đơn vị chỉ định, có thể xét timezone.

~~~javascript
{
  $dateTrunc: {
    date: "$createdAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Các unit thường dùng gồm **hour, day, week, month, quarter, year** và các đơn vị ngắn hơn. Tùy unit, có thêm **binSize** hoặc **startOfWeek**.

Ví dụ:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      createdAt: 1,
      localDayStart: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
]);
~~~

Với createdAt = 2025-05-31T17:01:00Z, đầu ngày địa phương 01/06/2025 ở Việt Nam là:

~~~text
2025-06-01 00:00 tại Asia/Ho_Chi_Minh
        = 2025-05-31T17:00:00Z
~~~

**Giá trị $dateTrunc trả về vẫn là một BSON Date đại diện cho instant UTC**, không phải một chuỗi "2025-06-01" và không mang tên timezone. Điều này rất quan trọng khi bạn đọc trường group key trong Java.

### 5.1. Không tưởng rằng dateTrunc luôn trả 00:00Z

~~~text
localDayStart = ISODate("2025-05-31T17:00:00Z")
~~~

Đây là đầu ngày **01/06 theo giờ Việt Nam**, không phải ngày 31/05 theo lịch doanh nghiệp. Nếu API chỉ serialize ISO UTC mà không cung cấp timezone/nhãn ngày tương ứng, người dùng có thể hiểu nhầm.

### 5.2. $dateTrunc cần MongoDB phiên bản tương thích

Các date operators hiện đại như **$dateTrunc**, **$dateAdd**, **$dateSubtract** và **$dateDiff** được giới thiệu trong MongoDB 5.0. Cần kiểm tra phiên bản MongoDB Server thật của dự án; chỉ nâng cấp thư viện Spring Data Java không làm một MongoDB Server cũ hỗ trợ operator mới.

## 6. $dateToString: chuyển bucket sang nhãn dễ hiển thị

Sau khi có đầu bucket là BSON Date, có thể tạo nhãn theo cùng múi giờ:

~~~javascript
{
  $dateToString: {
    date: "$createdAt",
    format: "%Y-%m-%d",
    timezone: "Asia/Ho_Chi_Minh",
    onNull: null
  }
}
~~~

Với instant 2025-05-31T17:01Z, nhãn ngày địa phương là **"2025-06-01"**.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 0,
      createdAt: 1,
      localDate: {
        $dateToString: {
          date: "$createdAt",
          format: "%Y-%m-%d",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
]);
~~~

Một số định dạng thông dụng:

| Mẫu format | Ý nghĩa |
| --- | --- |
| %Y-%m-%d | Nhãn ngày dạng năm-tháng-ngày |
| %Y-%m | Nhãn tháng |
| %Y-%m-%d %H:00 | Nhãn giờ địa phương |
| %G-W%V | Tuần ISO kèm **năm ISO**, nếu phiên bản server hỗ trợ định dạng tương ứng |

**Nhãn chuỗi là dữ liệu trình bày, không phải instant.** Nếu sau này cần tính khoảng thời gian thật giữa các bucket, nên giữ cả trường Date bucketStartUtc thay vì chỉ giữ chuỗi.

### 6.1. Nhóm theo chuỗi hay theo Date?

Có thể nhóm trực tiếp bằng dateToString với format YYYY-MM-DD, nhưng ưu tiên **dateTrunc trả BSON Date** khi cần:

- Sắp xếp theo thời gian.
- Tính toán ngày/giờ tiếp theo.
- Dùng giá trị đầu bucket làm định danh nhất quán.
- Phân biệt những giờ địa phương trùng nhãn trong ngày đổi DST.

Trong API báo cáo có thể giữ **bucketStartUtc** và **localDate** cùng nhau. Với báo cáo chỉ theo ngày ở một timezone cố định, chuỗi localDate là nhãn phù hợp nhưng không nên thay thế toàn bộ thông tin thời gian.

## 7. Pipeline đầu tiên: doanh thu theo ngày địa phương

Yêu cầu: tìm các Order của **shop-a**, trạng thái **PAID**, rồi tổng hợp theo **ngày của Asia/Ho_Chi_Minh**.

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "shop-a",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 },
      revenueMinor: { $sum: "$totalMinor" }
    }
  },
  { $sort: { _id: 1 } },
  {
    $project: {
      _id: 0,
      bucketStartUtc: "$_id",
      localDate: {
        $dateToString: {
          date: "$_id",
          format: "%Y-%m-%d",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: 1,
      revenueMinor: 1
    }
  }
]);
~~~

Pipeline có bốn bước:

1. **$match**: giới hạn tenant và status trước khi tính toán.
2. **$group**: tạo khóa nhóm bằng đầu ngày địa phương và cộng count/revenue.
3. **$sort**: sắp xếp các bucket theo instant thực.
4. **$project**: tạo nhãn ngày cho API và giữ giá trị đầu bucket UTC.

Với ba document mẫu, kết quả có dạng:

~~~javascript
[
  {
    bucketStartUtc: ISODate("2025-05-30T17:00:00Z"),
    localDate: "2025-05-31",
    orderCount: 1,
    revenueMinor: NumberLong("100000")
  },
  {
    bucketStartUtc: ISODate("2025-05-31T17:00:00Z"),
    localDate: "2025-06-01",
    orderCount: 2,
    revenueMinor: NumberLong("350000")
  }
]
~~~

**Lưu ý:** kết quả có thể dùng kiểu số BSON phù hợp với dữ liệu đầu vào và phép cộng. Khi viết DTO Java, đừng mặc định mọi số luôn được deserialize thành đúng một lớp Number cụ thể mà không kiểm tra mapping.

### 7.1. Nhóm trước rồi sort để tránh làm sai dữ liệu

Đối với metric tổng hợp theo ngày, **$sort: {_id:1}** sau $group sắp xếp các nhóm đã hình thành. Nếu muốn top-N ngày có doanh thu cao nhất, có thể sort theo revenueMinor sau $group. Đó là hai yêu cầu khác nhau.

Không dùng **$limit trước $group** nếu yêu cầu tính tổng toàn bộ đơn hàng khớp filter; làm vậy chỉ tính trên một tập con.

## 8. Lọc một ngày địa phương: tính ranh giới UTC trước

Người dùng chọn **ngày 01/06/2025** ở Asia/Ho_Chi_Minh. Khoảng thời gian cần tìm là:

~~~text
Đầu ngày địa phương: 2025-06-01 00:00 +07
   -> UTC: 2025-05-31T17:00:00Z

Đầu ngày kế tiếp:  2025-06-02 00:00 +07
   -> UTC: 2025-06-01T17:00:00Z
~~~

Truy vấn tốt hơn nên là khoảng **[startInclusive, endExclusive)**:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2025-05-31T17:00:00Z"),
    $lt: ISODate("2025-06-01T17:00:00Z")
  }
});
~~~

### 8.1. Vì sao dùng $lt thay vì $lte cuối ngày?

Không nên tự tạo “23:59:59.999” rồi dùng $lte nếu có thể biểu diễn khoảng nửa mở.

- Không phải đoán độ chính xác milisecond/microsecond/nanosecond của nguồn.
- Hai khoảng ngày liền nhau không trùng biên.
- Ghép ngày/tuần/tháng dễ hơn.
- Tránh sai khi DST khiến một ngày không đúng 24 giờ.

Quy tắc:

~~~text
startUtc <= createdAt < nextStartUtc
~~~

### 8.2. $match khoảng thời gian trước $group

Khi báo cáo chỉ yêu cầu một khoảng ngày, hãy đưa filter theo **createdAt BSON Date** vào $match trước các phép toán $dateTrunc. Điều này giúp MongoDB có cơ hội dùng index trên thời điểm gốc.

Trái lại, pipeline kiểu:

~~~javascript
{
  $match: {
    $expr: {
      $eq: [
        {
          $dateToString: {
            date: "$createdAt",
            format: "%Y-%m-%d",
            timezone: "Asia/Ho_Chi_Minh"
          }
        },
        "2025-06-01"
      ]
    }
  }
}
~~~

có thể phải tính biểu thức trên nhiều document và khó tận dụng index theo khoảng **createdAt** như một filter range trực tiếp. Nó vẫn có ngữ nghĩa hợp lệ trong một số use case, nhưng không nên là cách mặc định khi biết trước ranh giới UTC.

## 9. Java: đổi LocalDate sang khoảng Instant đúng múi giờ

Sử dụng **java.time**, không cộng cố định 86.400 giây để tìm đầu ngày kế tiếp.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2025, 6, 1);

Instant startInclusive = day.atStartOfDay(zone).toInstant();
Instant endExclusive = day.plusDays(1)
    .atStartOfDay(zone).toInstant();
~~~

Đây là cách tính đúng theo quy tắc của ZoneId. Với New York vào ngày bắt đầu DST, khoảng giữa hai nửa đêm địa phương có thể chỉ **23 giờ**; vào ngày kết thúc DST có thể **25 giờ**.

### 9.1. Filter bằng MongoTemplate

~~~java
import java.util.Date;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("tenantId").is("shop-a")
        .and("status").is("PAID")
        .and("createdAt")
        .gte(Date.from(startInclusive))
        .lt(Date.from(endExclusive))
);
~~~

Nếu entity dùng **Instant**, Spring Data vẫn có thể ánh xạ truy vấn thời gian với kiểu Date phù hợp ở tầng MongoDB. Khi viết raw BSON, Date.from là giá trị BSON Date rõ ràng để driver mã hóa.

### 9.2. Không tự cộng 24 giờ

Sai cho hệ thống có DST:

~~~java
Instant end = start.plusSeconds(24 * 60 * 60);
~~~

Đúng khi muốn khoảng **một ngày lịch** của một vùng:

~~~java
Instant end = day.plusDays(1)
    .atStartOfDay(zone)
    .toInstant();
~~~

**Một ngày lịch** khác với **một duration cố định 24 giờ**. Nếu nghiệp vụ thật sự yêu cầu “24 giờ qua” thì phép trừ Duration 24h lại là lựa chọn đúng; cần phân biệt hai câu hỏi.

## 10. Nhóm theo tuần: đầu tuần và năm ISO

Một tuần kinh doanh có thể bắt đầu thứ Hai hoặc Chủ nhật. Với **$dateTrunc**, xác định startOfWeek khi dùng unit week:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "week",
          startOfWeek: "monday",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả _id là **đầu tuần theo lịch địa phương**, được biểu diễn bằng BSON Date UTC.

### 10.1. Năm ISO không luôn bằng năm lịch

Các ngày sát Tết dương lịch có thể thuộc **năm ISO tuần trước/sau**. Ví dụ **01/01/2021** nằm trong **tuần ISO 53 của năm ISO 2020**.

Nếu dùng số tuần ISO, phải ghép **isoWeekYear + isoWeek** chứ không chỉ dùng year theo lịch và tuần theo ISO.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      isoWeekYear: {
        $isoWeekYear: {
          date: "$createdAt",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      isoWeek: {
        $isoWeek: {
          date: "$createdAt",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      isoDayOfWeek: {
        $isoDayOfWeek: {
          date: "$createdAt",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
]);
~~~

**ISO week** bắt đầu thứ Hai. Nếu doanh nghiệp định nghĩa tuần từ Chủ nhật hoặc một ngày khác, hãy dùng quy tắc kinh doanh nhất quán thay vì gọi mọi số tuần là ISO.

### 10.2. Bộ lọc tuần cũng cần đúng biên

Lấy **LocalDate của đầu tuần theo timezone**, đổi hai đầu mốc sang Instant, rồi dùng $match trên createdAt. Với báo cáo tuần nhiều tháng, điều này tránh phải tính tuần ISO cho mọi document trước khi lọc.

## 11. Nhóm theo tháng, quý và năm

Với **$dateTrunc**, các unit khác nhau chỉ cần thay đổi unit:

~~~javascript
// Đầu tháng địa phương.
{
  $dateTrunc: {
    date: "$createdAt",
    unit: "month",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

~~~javascript
// Đầu quý địa phương.
{
  $dateTrunc: {
    date: "$createdAt",
    unit: "quarter",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

~~~javascript
// Đầu năm địa phương.
{
  $dateTrunc: {
    date: "$createdAt",
    unit: "year",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Để nhóm theo tháng:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "shop-a", status: "PAID" } },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "month",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orders: { $sum: 1 },
      revenueMinor: { $sum: "$totalMinor" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Nếu doanh nghiệp sử dụng năm tài chính bắt đầu tháng 4, **unit quarter theo lịch** chưa chắc là quý tài chính mong muốn. Khi đó cần xây công thức fiscal riêng, hoặc tạo calendar dimension quy định đầu/kết kỳ.

### 11.1. Không lấy tháng bằng một chữ số

Nhóm chỉ theo **$month(createdAt)** sẽ gộp tháng 6 của mọi năm vào một nhóm. Muốn thống kê qua nhiều năm, phải giữ **năm** hoặc dùng dateTrunc unit month trả đầu tháng theo thời gian thực.

## 12. Nhóm theo giờ và vấn đề giờ lặp lại khi DST

Để nhóm theo từng giờ:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "hour",
          timezone: "America/New_York"
        }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Ở New York, có ngày **01:00–01:59 xuất hiện hai lần** khi đồng hồ lùi từ DST về giờ tiêu chuẩn. Hai khoảng giờ đó tương ứng với hai khoảng instant UTC khác nhau.

**Nếu nhóm chỉ bằng chuỗi local "2025-11-02 01:00"**, bạn có thể vô ý gộp hai giờ thực tế khác nhau thành một nhóm hoặc làm mất thông tin thứ tự.

Để báo cáo theo giờ:

- Giữ khóa bucket là BSON Date UTC khi cần phân biệt từng giờ thực.
- Trả thêm tên timezone và offset tương ứng khi trình bày.
- Xác định rõ nghiệp vụ muốn **gộp hai giờ địa phương trùng nhãn** hay tách chúng.
- Kiểm thử ngày đổi DST tại vùng được hỗ trợ.

### 12.1. Giờ không tồn tại

Ở ngày đổi sang DST, một số giờ đồng hồ địa phương có thể **không tồn tại**. Ví dụ tại một số khu vực, đồng hồ chuyển từ 01:59 trực tiếp sang 03:00.

Đừng tự tạo 24 nhãn giờ cho mọi ngày rồi ngầm coi mỗi nhãn có thời lượng đúng một giờ. Một biểu đồ “24 cột giờ” có thể cần quy tắc hiển thị riêng cho ngày 23/25 giờ.

## 13. $dateFromString: chuyển chuỗi giờ địa phương thành Date

Với dữ liệu legacy có chuỗi như:

~~~javascript
{
  sourceLocalTime: "2025-06-01 00:15:00",
  sourceTimezone: "Asia/Ho_Chi_Minh"
}
~~~

Muốn diễn giải chuỗi này thành một instant, cần chỉ định format và timezone:

~~~javascript
db.legacy_orders.aggregate([
  {
    $set: {
      parsedAt: {
        $dateFromString: {
          dateString: "$sourceLocalTime",
          format: "%Y-%m-%d %H:%M:%S",
          timezone: "$sourceTimezone",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
~~~

Khi sourceLocalTime = "2025-06-01 00:15:00" tại Asia/Ho_Chi_Minh, parsedAt tương ứng **2025-05-31T17:15:00Z**.

**onError: null** giúp pipeline không thất bại vì một chuỗi không parse được, nhưng có thể che giấu chất lượng dữ liệu. Khi migration, nên phân loại bản ghi parse lỗi và đưa vào danh sách cần xử lý, thay vì âm thầm bỏ qua.

### 13.1. Đừng chỉ định timezone hai lần

Nếu dateString đã chứa thông tin timezone/offset như "2025-06-01T00:15:00Z", không kết hợp tùy tiện với tham số timezone khác để diễn giải lại. $dateFromString có quy tắc riêng về chuỗi mang timezone; việc cùng chỉ định thông tin múi giờ trong input và tham số có thể dẫn đến lỗi.

Tốt nhất là thống nhất schema nguồn:

- Chuỗi **không có timezone** → dùng timezone nguồn được xác thực.
- Chuỗi **có offset/UTC** → parse theo offset/UTC đó.
- Dữ liệu thời gian **không rõ timezone** → không tự đoán khi báo cáo có yêu cầu chính xác.

### 13.2. Ngày giờ mơ hồ tại DST

Một chuỗi như "2025-11-02 01:30:00" tại America/New_York có thể tương ứng với **hai instant** trong ngày lùi đồng hồ. Nếu nguồn không lưu offset hoặc thông tin phân biệt, không thể khôi phục một instant duy nhất từ chuỗi đó bằng suy đoán chắc chắn.

Khi nhập dữ liệu quan trọng, ưu tiên nguồn cung cấp **UTC instant hoặc offset tại thời điểm sự kiện**.

## 14. $dateToParts và bộ phận lịch

Nếu một báo cáo cần tách năm, tháng, ngày, giờ theo timezone, MongoDB có **$dateToParts**:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 0,
      localParts: {
        $dateToParts: {
          date: "$createdAt",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
]);
~~~

Một kết quả có dạng object với các field năm, tháng, ngày, giờ, phút, giây và mili giây theo vùng được chỉ định.

Nếu cần ISO week calendar, có thể xem tùy chọn **iso8601** của các biểu thức date parts tương thích; luôn kiểm chứng tên field kết quả và semantics trên server version đang dùng.

### 14.1. Khi nào dùng $dateToParts?

Phù hợp khi:

- Báo cáo cần phân tổ theo **giờ trong ngày** (0–23) và ngày trong tuần.
- Ứng dụng cần các trường số năm/tháng/ngày để tạo composite key.
- Phân tích các mẫu theo lịch thay vì chỉ bucket một interval.

Nhưng nếu mục đích đơn giản là **nhóm từng ngày lịch**, $dateTrunc thường rõ hơn và giữ được instant đầu bucket.

## 15. $dateAdd, $dateSubtract và $dateDiff

Không phải mọi câu hỏi về thời gian đều là bài toán grouping. MongoDB còn hỗ trợ cộng/trừ khoảng thời gian và tính chênh lệch theo đơn vị lịch.

### 15.1. $dateAdd: cộng một đơn vị lịch

~~~javascript
db.orders.aggregate([
  {
    $project: {
      createdAt: 1,
      nextLocalDaySameTime: {
        $dateAdd: {
          startDate: "$createdAt",
          unit: "day",
          amount: 1,
          timezone: "America/New_York"
        }
      }
    }
  }
]);
~~~

Khi dùng **timezone** và đơn vị từ ngày trở lên, phép cộng dựa trên lịch của vùng tương ứng, có thể chịu tác động của DST. Nó không nhất thiết giống cộng 86.400 giây.

Ví dụ tại New York:

~~~text
2025-03-09 00:00 (UTC-05) -> 2025-03-09T05:00:00Z
Sau 1 ngày lịch:
2025-03-10 00:00 (UTC-04) -> 2025-03-10T04:00:00Z

Chênh lệch instant: 23 giờ
~~~

Nếu chính sách nghiệp vụ là **hết hạn sau chính xác 24 giờ**, hãy dùng thời lượng 24 giờ thay vì “1 ngày theo lịch địa phương”. Nếu là **hết hạn vào cùng giờ của ngày hôm sau ở New York**, hãy dùng lịch và timezone phù hợp.

### 15.2. $dateSubtract: trừ theo lịch

~~~javascript
{
  $dateSubtract: {
    startDate: "$createdAt",
    unit: "month",
    amount: 1,
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Ví dụ “lùi một tháng” không đồng nghĩa “trừ 30 ngày”. Các tháng có số ngày khác nhau, và phép cộng/trừ tháng ở ngày cuối tháng có quy tắc xử lý giới hạn ngày. Hãy kiểm thử những trường hợp 28/29/30/31 và năm nhuận cho nghiệp vụ dự kiến.

### 15.3. $dateDiff: đếm ranh giới theo đơn vị

~~~javascript
{
  $dateDiff: {
    startDate: "$createdAt",
    endDate: "$shippedAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

**$dateDiff theo unit=day là phép tính chênh lệch theo đơn vị lịch**, không phải số giờ thực chia 24 rồi làm tròn theo ý của ứng dụng. Nó trả số nguyên ứng với những ranh giới của unit được tính theo quy tắc operator.

Phân biệt hai chỉ số:

| Câu hỏi | Cách xử lý |
| --- | --- |
| Đã trôi qua bao nhiêu giờ thực? | Dùng chênh lệch instant theo giờ/mili giây. |
| Đã đi qua bao nhiêu ranh giới ngày theo New York? | $dateDiff unit day, timezone America/New_York. |
| Ngày lịch thứ N sau ngày đặt hàng là ngày nào? | $dateAdd unit day theo timezone nghiệp vụ. |
| Thời điểm đúng 24 giờ sau khi thanh toán? | Cộng duration 24 giờ, không đánh đồng với ngày lịch. |

**Không đưa một biểu thức $dateDiff vào hợp đồng SLA nếu chưa thống nhất cách đếm ngày làm việc, ngày nghỉ và timezone.** DateDiff không tự bỏ qua cuối tuần hay ngày lễ.

## 16. Nhóm theo khung thời gian nhiều đơn vị: binSize

Khi cần biểu đồ mỗi 15 phút hoặc mỗi 2 giờ, **$dateTrunc** có tham số **binSize**:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "minute",
          binSize: 15,
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orders: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Các bucket phút có thể là 00, 15, 30 và 45, tùy thời điểm tham chiếu và quy tắc truncation của operator. Với một biểu đồ theo từng 15 phút, cách này phù hợp hơn việc tự cắt chuỗi rồi nối nhãn.

### 16.1. Bucket theo 7 ngày không luôn là tuần nghiệp vụ

Nếu yêu cầu “tuần bắt đầu thứ Hai”, ưu tiên:

~~~javascript
{
  $dateTrunc: {
    date: "$createdAt",
    unit: "week",
    startOfWeek: "monday",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Không thay bằng **unit day, binSize 7** rồi mặc định kết quả trùng với tuần ISO hoặc tuần doanh nghiệp. Các bucket 7 ngày và ranh giới tuần có thể được neo theo những quy tắc khác.

### 16.2. Không dùng binSize để tạo lịch tài chính tùy biến một cách mù quáng

Một quý tài chính bắt đầu khác tháng 1, kỳ 4-4-5 tuần hoặc lịch bán lẻ đặc biệt có thể không được mô tả đúng bằng một dateTrunc đơn giản. Hãy xác định kỳ báo cáo dựa trên một lịch được duyệt và kiểm thử ranh giới kỳ.

## 17. Triển khai báo cáo ngày bằng MongoTemplate

Ví dụ Spring Data MongoDB dưới đây dùng **MongoTemplate** và **AggregationOperation**. Các stage được viết bằng **org.bson.Document** nhằm minh họa trực tiếp operator BSON, tránh phụ thuộc vào tên hàm builder có thể thay đổi giữa các thế hệ thư viện.

Vì dùng raw Document, các tên field **tenantId, status, createdAt, totalMinor** trong mã phải đúng **tên BSON thực**. Nếu entity có @Field để đổi tên BSON, hãy sửa stage tương ứng hoặc sử dụng API aggregation có mapping qua entity metadata.

### 17.1. DTO kết quả

~~~java
package com.example.reports;

import java.time.LocalDate;

public record DailyOrderSummary(
    LocalDate localDate,
    long orderCount,
    long revenueMinor
) {}
~~~

DTO công bố **localDate** theo timezone đã chọn. Một API thực nên trả thêm metadata như **timezone**, start/end đã sử dụng và metric definition để client hiểu kết quả.

### 17.2. Service với $match và $dateTrunc

~~~java
package com.example.reports;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;

public class DailyOrderReportService {

    private final MongoTemplate template;

    public DailyOrderReportService(MongoTemplate template) {
        this.template = template;
    }

    public List<DailyOrderSummary> report(
            String tenantId,
            LocalDate fromInclusive,
            LocalDate toExclusive,
            ZoneId zone) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant is required");
        }
        if (fromInclusive == null || toExclusive == null
                || !fromInclusive.isBefore(toExclusive)
                || zone == null) {
            throw new IllegalArgumentException("Invalid range/zone");
        }

        Instant start = fromInclusive.atStartOfDay(zone).toInstant();
        Instant end = toExclusive.atStartOfDay(zone).toInstant();

        AggregationOperation match = context ->
            new Document("$match",
                new Document("tenantId", tenantId)
                    .append("status", "PAID")
                    .append("createdAt",
                        new Document("$gte", Date.from(start))
                            .append("$lt", Date.from(end))));

        AggregationOperation group = context ->
            new Document("$group",
                new Document("_id",
                    new Document("$dateTrunc",
                        new Document("date", "$createdAt")
                            .append("unit", "day")
                            .append("timezone", zone.getId())))
                    .append("orderCount", new Document("$sum", 1))
                    .append("revenueMinor",
                        new Document("$sum", "$totalMinor")));

        AggregationOperation sort = context ->
            new Document("$sort", new Document("_id", 1));

        Aggregation pipeline =
            Aggregation.newAggregation(match, group, sort);

        List<Document> buckets = template.aggregate(
            pipeline,
            "orders",
            Document.class
        ).getMappedResults();

        return buckets.stream()
            .map(bucket -> toSummary(bucket, zone))
            .toList();
    }

    public static DailyOrderSummary toSummary(
            Document bucket, ZoneId zone) {

        LocalDate day = bucket.getDate("_id")
            .toInstant()
            .atZone(zone)
            .toLocalDate();

        long count =
            ((Number) bucket.get("orderCount")).longValue();
        long revenue =
            ((Number) bucket.get("revenueMinor")).longValue();

        return new DailyOrderSummary(day, count, revenue);
    }
}
~~~

**Điểm thiết kế quan trọng:**

1. Tính **from/to** từ LocalDate và ZoneId trước khi truy vấn.
2. $match theo Date thực, sử dụng khoảng **[start, end)** và tenant/status.
3. $group theo **$dateTrunc** unit day và cùng timezone.
4. $sort theo _id là instant đầu bucket.
5. Chuyển _id Date thành LocalDate bằng **cùng ZoneId** lúc tạo kết quả.
6. Sử dụng **Number.longValue()** để không phụ thuộc vào việc BSON accumulator trả int hay long khi tổng còn trong giới hạn.

Ví dụ giả định **totalMinor** được lưu theo kiểu số nguyên và tổng không tràn miền long. Nếu lưu Decimal128, số tiền rất lớn hoặc nhiều loại tiền tệ, phải thiết kế kiểu kết quả/rounding riêng; không cộng tiền từ các đồng tiền khác nhau rồi gọi đó là một doanh thu duy nhất.

### 17.3. Vì sao không gọi dateToString rồi group ngay?

DateToString tạo nhãn hiển thị, nhưng **DateTrunc tạo bucket theo instant**. Với ngày địa phương, cả hai có thể được dùng nếu hợp đồng rõ ràng; với giờ có DST, nhóm theo Date trước giúp giữ ranh giới thực, tránh vô tình gộp các nhãn 01:00 trùng nhau.

### 17.4. Raw stage và field mapping

Raw AggregationOperation ở trên gửi **tên BSON đã viết**. Ví dụ nếu Java entity dùng:

~~~java
@Field("paid_at")
private Instant paidAt;
~~~

thì raw stage phải tham chiếu **"$paid_at"**, không phải **"$paidAt"**. Các aggregation operations được ánh xạ theo entity có thể giúp xử lý tên property; đừng trộn hai cách mà chưa kiểm tra BSON pipeline cuối cùng.

## 18. Sử dụng builder Spring Data thay vì raw Document

Spring Data MongoDB có các API aggregation như:

~~~java
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.MatchOperation;
import org.springframework.data.mongodb.core.aggregation.SortOperation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.domain.Sort;

MatchOperation match = Aggregation.match(
    Criteria.where("tenantId").is("shop-a")
        .and("status").is("PAID")
);

SortOperation sort = Aggregation.sort(
    Sort.Direction.ASC, "_id"
);
~~~

Ngoài ra còn có nhóm **DateOperators** của Spring Data MongoDB cho nhiều biểu thức ngày giờ. Tuy nhiên, **tên method cụ thể** như DateTrunc, DateToString, DateDiff, cách truyền timezone, unit và nested expressions phụ thuộc phiên bản thư viện.

Khi muốn code có kiểu hơn, hãy:

1. Kiểm tra API **DateOperators** thực có trong Spring Data MongoDB đang dùng.
2. Dùng **Aggregation.project()**, **Aggregation.group()**, **Aggregation.match()** nếu chúng diễn đạt đủ yêu cầu.
3. Với operator chưa có builder thuận tiện, dùng custom **AggregationOperation** tạo BSON như phần 17.
4. Kiểm tra pipeline BSON đầu ra và so sánh với mongosh.
5. Không viết một method builder không tồn tại chỉ vì tên giống MongoDB operator.

**Không cần tự viết hoặc chạy một aggregation nhiều stage chỉ để dùng DateOperators.** Với điều kiện đơn giản cần lấy document theo ngày, MongoTemplate Query range có thể là lựa chọn nhẹ hơn.

## 19. ReactiveMongoTemplate và luồng kết quả theo ngày

Với reactive stack, giữ cùng ranh giới ngày/timezone và pipeline, nhưng trả **Flux** thay vì đọc List đồng bộ:

~~~java
import java.time.ZoneId;
import org.bson.Document;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import reactor.core.publisher.Flux;

public Flux<DailyOrderSummary> reportReactive(
        ReactiveMongoTemplate template,
        Aggregation pipeline,
        ZoneId zone) {

    return template.aggregate(
        pipeline, "orders", Document.class
    ).map(bucket ->
        DailyOrderReportService.toSummary(bucket, zone)
    );
}
~~~

Ở đây **pipeline** được xây từ cùng các stage $match/$group/$sort như phần trước, và **toSummary** là hàm chuyển đổi tĩnh. Spring WebFlux hoặc caller subscribe publisher để thực thi query.

### 19.1. Reactive không đổi semantics của timezone

Một pipeline dùng **"Asia/Ho_Chi_Minh"** cho $dateTrunc không tự trở thành **UTC grouping** chỉ vì dùng ReactiveMongoTemplate. MongoDB Server vẫn thực hiện toán tử với timezone được cung cấp.

### 19.2. Không block hoặc collect vô hạn

Tránh:

~~~java
// Không nên trong reactive service/controller.
var rows = template.aggregate(
    pipeline, "orders", Document.class
).collectList().block();
~~~

Nếu một API cần mảng kết quả hữu hạn (chẳng hạn tối đa 31 bucket ngày), **collectList()** sau một $match có khoảng hữu hạn có thể chấp nhận được trong reactive pipeline, nhưng không gọi **block()** trên event loop.

### 19.3. Mỗi subscription có thể chạy lại aggregation

Đừng tự subscribe() để “khởi động” publisher rồi lại trả nó cho controller. Có thể làm tăng tải MongoDB và thu hai kết quả khác nhau nếu dữ liệu được insert/xóa giữa các lần query.

## 20. Index và vị trí các stage trong pipeline

Một index cần đánh giá cho báo cáo tenant/status/time:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: 1
});
~~~

Ý tưởng là đặt **hai field so sánh bằng** trước field khoảng thời gian, giúp $match có cơ hội dùng compound index.

### 20.1. $match trước $group

~~~mermaid
flowchart LR
    A["Collection orders"] --> B["$match tenant/status/UTC range"]
    B --> C["$group theo $dateTrunc(timezone)"]
    C --> D["$sort bucketStartUtc"]
    D --> E["DTO báo cáo"]
~~~

Với báo cáo chỉ cần ngày 01–30/06 ở Việt Nam, nên tính UTC start/end cho **cả khoảng báo cáo**, rồi giới hạn trước khi group. Không cần tính dateToString cho mọi document lịch sử.

### 20.2. Vì sao projection không tự làm query nhanh?

Nếu pipeline chỉ trả 30 dòng nhóm, server vẫn có thể phải đọc hoặc duyệt rất nhiều order để cộng doanh thu. Giảm kích thước response không tự giảm chi phí $group hoặc giúp filter dùng index.

Nếu cần báo cáo thường xuyên trên hàng tỷ sự kiện, có thể cân nhắc:

- Materialized daily summaries theo tenant/timezone/metric.
- Xử lý incremental có idempotency và đối soát.
- Time-series design khi dữ liệu phù hợp.
- Retention/partitioning và query theo khoảng hữu hạn.

Nhưng **summary cache** cần quy định xử lý đơn hàng đến trễ, hủy/hoàn tiền và thay đổi timezone của tenant. Không được chỉ cộng mới rồi gọi số liệu “chính xác” nếu dữ liệu cũ có thể được điều chỉnh.

### 20.3. Sử dụng explain("executionStats")

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "shop-a",
      status: "PAID",
      createdAt: {
        $gte: ISODate("2025-05-31T17:00:00Z"),
        $lt: ISODate("2025-06-30T17:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orders: { $sum: 1 }
    }
  }
]);
~~~

Quan sát đường thực thi:

| Chỉ số/thành phần | Câu hỏi |
| --- | --- |
| winningPlan | MongoDB có dùng index dự kiến không? |
| totalKeysExamined | Bao nhiêu index key đã được duyệt? |
| totalDocsExamined | Bao nhiêu document gốc cần đọc? |
| nReturned | Bao nhiêu kết quả được trả/được tổng hợp? |
| SORT stage | Có sort ngoài index không? |
| GROUP / aggregation stages | Pipeline có phải xử lý tập lớn không? |
| executionTimeMillis | Độ trễ ở điều kiện thử nghiệm ra sao? |

Hình dạng explain thay đổi theo phiên bản MongoDB và execution engine. Hãy quan sát thực tế thay vì viết code phụ thuộc cứng vào cấu trúc explain cụ thể.

## 21. Ngày không có dữ liệu và bucket rỗng

$group chỉ tạo nhóm cho những document khớp. Nếu ngày 02/06 không có Order, pipeline có thể **không trả bản ghi nào cho ngày đó**.

Ví dụ dữ liệu:

~~~text
2025-06-01 -> 2 orders
2025-06-02 -> không có order
2025-06-03 -> 1 order
~~~

Kết quả từ $group thông thường:

~~~json
[
  { "localDate": "2025-06-01", "orderCount": 2 },
  { "localDate": "2025-06-03", "orderCount": 1 }
]
~~~

Trong biểu đồ cần một điểm cho mọi ngày, có thể **fill ngày thiếu ở tầng ứng dụng** bằng LocalDate:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<LocalDate, DailyOrderSummary> byDate =
    reportRows.stream().collect(Collectors.toMap(
        DailyOrderSummary::localDate,
        Function.identity()
    ));

List<DailyOrderSummary> completed = fromInclusive
    .datesUntil(toExclusive)
    .map(day -> byDate.getOrDefault(
        day,
        new DailyOrderSummary(day, 0L, 0L)
    ))
    .toList();
~~~

Đoạn code giả định **reportRows, fromInclusive, toExclusive** đã được tạo trong service. **datesUntil** tạo dãy LocalDate theo ngày lịch và không cần giả định mỗi ngày dài 24 giờ.

### 21.1. Dùng $densify hay $fill?

MongoDB có các stage như **$densify** và **$fill** trên những phiên bản hỗ trợ, giúp làm đầy chuỗi dữ liệu theo quy tắc nhất định. Tuy nhiên, nếu bucket đầu ngày địa phương được biểu diễn bằng các instant UTC có khoảng cách **23/25 giờ khi đổi DST**, việc tự động densify bằng bước **24 giờ UTC** có thể làm sai mốc.

Với báo cáo theo **ngày lịch của từng timezone**, cách fill bằng LocalDate ở tầng API hoặc một lịch nghiệp vụ được xác nhận thường dễ hiểu và dễ kiểm thử hơn.

### 21.2. Phân biệt zero và missing

Không có document cho ngày 02/06 có thể được trình bày là **0 orders**, nhưng cần đảm bảo nguồn dữ liệu đã đầy đủ. Trong pipeline chưa hoàn tất nhập dữ liệu, missing đôi khi có nghĩa “chưa có dữ liệu” chứ không phải thật sự bằng 0. Hợp đồng báo cáo nên có ngữ nghĩa rõ.

## 22. Những lỗi nghiêm trọng về timezone và dữ liệu

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Đơn lúc 00:05 bị tính vào ngày trước | Group theo UTC thay vì timezone nghiệp vụ | Đưa timezone vào $dateTrunc |
| localDate hiển thị lệch một ngày | Serialize bucketStartUtc như ngày địa phương | Đổi bucket instant sang ZoneId trước khi lấy LocalDate |
| Range lọc thiếu các đơn đầu ngày | $match dùng ngày UTC 00:00 thay vì local midnight | Tính UTC boundaries từ LocalDate + ZoneId |
| Hai báo cáo cùng ngày có số khác nhau | Dùng timezone khác nhau | Công bố timezone và metric definition |
| Mất/gộp giờ khi đổi DST | Group theo chuỗi giờ địa phương | Giữ UTC bucket key, xử lý offset |
| Ngày DST tính 24h trong mọi trường hợp | Cộng 86.400 giây | Tính đầu ngày kế bằng atStartOfDay(zone) |
| Tuần cuối năm bị gán sai năm | Dùng year thường với isoWeek | Dùng isoWeekYear + isoWeek |
| Tháng 6 của hai năm bị gộp | Chỉ group theo $month | Dùng dateTrunc month hoặc năm + tháng |
| $dateTrunc không được nhận diện | MongoDB Server quá cũ | Kiểm tra yêu cầu version MongoDB 5.0+ |
| $dateFromString thất bại | Format/offset/timezone không khớp | Chuẩn hóa nguồn; onError + báo lỗi dữ liệu |
| Nhiều document vào bucket null | createdAt null/missing/sai kiểu | Kiểm tra $type, validate trước group |
| Kết quả “doanh thu” không đúng | Dùng createdAt dù nghiệp vụ yêu cầu paidAt | Đổi event timestamp theo định nghĩa metric |
| $group rất chậm | $match thiếu index hoặc ở sau date expression | Match theo range Date trước group |
| Giờ local trùng nhãn | Chỉ có chuỗi HH không có offset | Giữ bucket UTC/offset trong response |
| Tính tiền sai | Trộn currency hoặc dùng double | Chọn minor units/Decimal128, nhóm theo currency |
| Test chạy khác nhau giữa môi trường | Quy tắc timezone/driver/server khác nhau | Chuẩn hóa môi trường, kiểm thử DST và zone data |

### 22.1. Pipeline phải xử lý document có thời gian lỗi

Nếu lịch sử có createdAt dạng String/null, có thể cân nhắc filter theo kiểu:

~~~javascript
{
  $match: {
    tenantId: "shop-a",
    status: "PAID",
    createdAt: { $type: "date" }
  }
}
~~~

Đây là cách loại dữ liệu không phải BSON Date khỏi metric, **nhưng không phải giải pháp sửa dữ liệu**. Báo cáo nên ghi nhận số document bị bỏ qua do schema lỗi để người vận hành có thể xử lý.

Nếu viết aggregation migration với $dateFromString, đừng dùng onError:null rồi mặc định các record null trong $group là “ngày không xác định” mà không báo cáo.

## 23. Kiểm thử tích hợp MongoDB: ranh giới ngày Việt Nam

Chỉ test một hàm Java tính timezone là chưa đủ: phải chứng minh MongoDB thực thi $dateTrunc và filter UTC theo cùng kết quả.

Ví dụ JUnit 5 với Spring Boot test slice và MongoDB test instance:

~~~java
package com.example.reports;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;
import java.util.List;
import java.util.UUID;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import com.mongodb.client.model.Filters;

@DataMongoTest
class DailyOrderReportTest {

    @Autowired
    MongoTemplate template;

    private Document order(
            String tenant, String instant, long totalMinor) {
        return new Document("_id", new ObjectId())
            .append("tenantId", tenant)
            .append("status", "PAID")
            .append("createdAt",
                Date.from(Instant.parse(instant)))
            .append("totalMinor", totalMinor);
    }

    @Test
    void groupsByLocalDayInsteadOfUtcDay() {
        String tenant = "TEST-" + UUID.randomUUID();
        var collection = template.getCollection("orders");

        try {
            collection.insertMany(List.of(
                order(tenant, "2025-05-31T16:59:00Z", 100_000L),
                order(tenant, "2025-05-31T17:01:00Z", 200_000L),
                order(tenant, "2025-06-01T01:00:00Z", 150_000L)
            ));

            DailyOrderReportService service =
                new DailyOrderReportService(template);

            List<DailyOrderSummary> rows = service.report(
                tenant,
                LocalDate.of(2025, 6, 1),
                LocalDate.of(2025, 6, 2),
                ZoneId.of("Asia/Ho_Chi_Minh")
            );

            assertThat(rows).hasSize(1);
            assertThat(rows.get(0).localDate())
                .isEqualTo(LocalDate.of(2025, 6, 1));
            assertThat(rows.get(0).orderCount())
                .isEqualTo(2L);
            assertThat(rows.get(0).revenueMinor())
                .isEqualTo(350_000L);
        } finally {
            collection.deleteMany(Filters.eq("tenantId", tenant));
        }
    }
}
~~~

Test xác nhận document lúc **16:59Z** thuộc ngày 31/05 ở Việt Nam và **không** được tính vào báo cáo 01/06, trong khi hai document **17:01Z** và **01:00Z** được tính.

**Không chạy test trên database production.** Dùng MongoDB server/instance test phiên bản hỗ trợ $dateTrunc, và đặt tenant riêng cho fixture để dọn đúng dữ liệu.

### 23.1. Test timezone mùa hè và ngày 23 giờ

Một test thuần Java giúp xác nhận cách thiết kế UTC boundaries:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import org.junit.jupiter.api.Test;

@Test
void newYorkDstStartHasTwentyThreeHours() {
    ZoneId zone = ZoneId.of("America/New_York");
    LocalDate day = LocalDate.of(2025, 3, 9);

    Instant start = day.atStartOfDay(zone).toInstant();
    Instant end = day.plusDays(1)
        .atStartOfDay(zone).toInstant();

    assertThat(start)
        .isEqualTo(Instant.parse("2025-03-09T05:00:00Z"));
    assertThat(end)
        .isEqualTo(Instant.parse("2025-03-10T04:00:00Z"));
    assertThat(Duration.between(start, end).toHours())
        .isEqualTo(23L);
}
~~~

Để kiểm tra MongoDB, seed các sự kiện ở sát **start/end** của ngày đó và xác minh $dateTrunc với America/New_York tạo đúng localDay. Test tương tự cho ngày kết thúc DST có thể cho **25 giờ**.

### 23.2. Ma trận test cần bổ sung

| Trường hợp | Kỳ vọng |
| --- | --- |
| 1 giây trước đầu ngày local | Không thuộc ngày mới |
| Đúng đầu ngày local | Thuộc ngày mới |
| Đúng đầu ngày hôm sau | Không thuộc ngày trước vì endExclusive |
| Hai Order cùng UTC date nhưng khác local date | Nhóm khác theo timezone |
| Ngày có 23 giờ | Không thiếu/đếm thừa vì cộng 24h |
| Ngày có 25 giờ | Xử lý giờ lặp lại |
| 01/01 rơi vào ISO week-year trước | Nhãn tuần ISO chính xác |
| Document createdAt null | Không vô tình trộn vào bucket ngày thật |
| Data chứa String timestamp | Được chuẩn hóa hoặc báo lỗi đúng |
| Order khác tenant hoặc status khác | Không vào báo cáo |
| Báo cáo không có Order | Trả rỗng hoặc được fill thành zero theo hợp đồng |
| Số tiền quá lớn / khác currency | Có chính sách numeric/currency rõ |
| ZoneId không hợp lệ | Từ chối request |
| Server thiếu $dateTrunc | Kiểm tra tương thích trước khi triển khai |

## 24. Bài tập thực hành

### Bài tập 1: nhóm theo ngày nào?

createdAt = 2025-05-31T17:30:00Z. Ngày theo Asia/Ho_Chi_Minh là gì?

**Đáp án:** 2025-06-01, vì giờ địa phương là 00:30 ngày 01/06/2025.

### Bài tập 2: $dateTrunc đúng timezone

Viết expression lấy đầu ngày ở Việt Nam:

~~~javascript
{
  $dateTrunc: {
    date: "$createdAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

**Lưu ý:** giá trị trả về là BSON Date/instant, không phải string YYYY-MM-DD.

### Bài tập 3: lọc đúng một ngày

Yêu cầu ngày 01/06/2025 tại Asia/Ho_Chi_Minh. Khoảng UTC nào đúng?

**Đáp án:** [2025-05-31T17:00:00Z, 2025-06-01T17:00:00Z). Dùng $gte đầu và $lt cuối.

### Bài tập 4: không dùng 24h cố định

Tại New York, ngày 09/03/2025 bắt đầu 05:00Z và ngày sau bắt đầu 04:00Z. Vì sao chỉ 23 giờ?

**Đáp án:** đồng hồ chuyển sang giờ mùa hè, bỏ qua một giờ địa phương. Ngày lịch không nhất thiết dài 24 giờ.

### Bài tập 5: tuần ISO

Ngày 01/01/2021 thuộc năm ISO nào và tuần ISO thứ mấy?

**Đáp án:** năm ISO **2020**, tuần ISO **53**. Phải dùng isoWeekYear và isoWeek cùng timezone.

### Bài tập 6: tháng qua nhiều năm

Một pipeline chỉ group theo **$month(createdAt)**. Điều gì xảy ra với dữ liệu tháng 6 của năm 2024 và 2025?

**Đáp án:** có thể bị gộp vào cùng nhóm số 6. Dùng dateTrunc unit month hoặc key gồm cả năm và tháng.

### Bài tập 7: biểu thức cộng ngày

Nghiệp vụ yêu cầu hết hạn “vào cùng giờ địa phương của ngày hôm sau”. Dùng phép cộng 86.400 giây có luôn đúng không?

**Đáp án:** không tại vùng có DST. Dùng cộng một ngày theo lịch với timezone, ví dụ $dateAdd unit day, amount 1, timezone phù hợp.

### Bài tập 8: dateFromString

Nguồn lưu "2025-06-01 00:15:00" không có timezone. Có thể biết instant chính xác không?

**Đáp án:** không nếu không biết timezone nguồn. Khi có Asia/Ho_Chi_Minh, parse thành 2025-05-31T17:15:00Z.

### Bài tập 9: index và $match

Một báo cáo chỉ cần tháng 6 nhưng pipeline tạo dateToString cho cả collection rồi mới lọc. Nên cải thiện thế nào?

**Đáp án:** tính UTC start/end cho tháng 6 theo timezone nghiệp vụ, $match theo tenant/status/createdAt trước $group; đánh giá compound index tương ứng.

### Bài tập 10: group giờ có DST

Vì sao không luôn group bằng chuỗi "%Y-%m-%d %H" tại America/New_York?

**Đáp án:** ngày kết thúc DST có hai giờ địa phương mang nhãn 01:00 nhưng là hai instant khác nhau. Giữ khóa bucket UTC và thêm offset/zone khi hiển thị.

### Bài tập 11: ngày thiếu dữ liệu

$group trả 01/06 và 03/06, không có 02/06. Có bắt buộc $group trả một bucket 0 cho 02/06 không?

**Đáp án:** không. $group chỉ tạo nhóm có dữ liệu; cần fill calendar ở API hoặc bằng chiến lược aggregation được kiểm chứng nếu muốn hiển thị ngày rỗng.

### Bài tập 12: Java conversion

Từ **LocalDate(2025-06-01)** và ZoneId("Asia/Ho_Chi_Minh"), viết cách tính hai đầu biên:

~~~java
Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();
~~~

**Giải thích:** phép tính dựa trên lịch địa phương, không cộng cố định 24 giờ.

### Bài tập 13: reactive

ReactiveMongoTemplate.aggregate trả Flux, bạn muốn DTO cho từng bucket. Có nên block trước khi map không?

**Đáp án:** không. Dùng **.map(...)** trên Flux và để WebFlux/caller subscribe; giới hạn thời gian truy vấn ở MongoDB trước.

### Bài tập 14: sai nghĩa doanh thu

Order được tạo ngày 31/05 nhưng thanh toán ngày 01/06. Báo cáo doanh thu theo ngày thanh toán nên group theo field nào?

**Đáp án:** **paidAt**, nếu đó là định nghĩa metric. Không dùng createdAt chỉ vì field có sẵn.

## 25. Checklist trước khi đưa báo cáo thời gian lên production

- **Metric:** có phân biệt createdAt, paidAt, canceledAt, refundedAt không?
- **Kiểu BSON:** timestamp có thực sự lưu dưới BSON Date không?
- **Timezone:** dùng UTC, timezone tenant hay timezone người xem?
- **Timezone ID:** giá trị IANA được validate và có chính sách thay đổi không?
- **Ranh giới:** startInclusive/endExclusive được tạo từ lịch local chưa?
- **Pipeline:** $match theo Date range đặt trước các biểu thức grouping chưa?
- **Bucket:** $dateTrunc dùng đúng unit, binSize, startOfWeek và timezone chưa?
- **Nhãn:** API có công bố timezone và tránh nhầm UTC bucket với local date không?
- **DST:** đã test ngày có 23/25 giờ và giờ địa phương trùng nhãn chưa?
- **ISO week:** đã ghép isoWeekYear/isoWeek đúng không?
- **Tháng/quý:** đã phân biệt lịch thông thường và fiscal calendar chưa?
- **Dữ liệu lỗi:** có thống kê document timestamp null/không đúng kiểu không?
- **Dữ liệu trễ:** summary cache có cơ chế cập nhật/bù trừ không?
- **Zero buckets:** cách hiển thị ngày không có dữ liệu đã được chốt chưa?
- **Numeric:** dùng minor units/Decimal128 và tách currency phù hợp chưa?
- **Version:** MongoDB Server có hỗ trợ các date operators đang sử dụng chưa?
- **Index:** đã kiểm tra winningPlan/keysExamined/docsExamined chưa?
- **Reactive:** pipeline không block và không bị subscribe lặp chưa?
- **Testing:** đã có integration tests với ranh giới ngày và timezone khác nhau chưa?

## 26. Tổng kết

1. **BSON Date là instant**, không lưu múi giờ hay ngày lịch địa phương.
2. **Timezone xác định ranh giới ngày/tuần/tháng**, vì vậy cùng dữ liệu có thể cho grouping khác nhau theo vùng.
3. **$dateTrunc** tạo khóa bucket dạng BSON Date; **$dateToString** tạo nhãn trình bày; hai operator có mục tiêu khác nhau.
4. **$dateFromString** dùng để diễn giải chuỗi thời gian với format/timezone rõ ràng; phải xử lý dữ liệu lỗi và DST.
5. **$dateAdd, $dateSubtract, $dateDiff** cần được chọn theo ngữ nghĩa lịch hoặc duration, không đánh đồng ngày với 24 giờ.
6. **Lọc theo khoảng UTC [start, end)** được tính từ LocalDate + ZoneId giúp tránh lệch ranh giới và hỗ trợ index.
7. **Tuần ISO phải đi cùng năm ISO**, và các ngày gần đầu năm là ca kiểm thử quan trọng.
8. **Nhóm theo giờ ở vùng DST cần giữ UTC bucket key** để tránh làm mất thông tin những giờ lặp lại.
9. **MongoTemplate và ReactiveMongoTemplate dùng cùng semantics MongoDB**, khác cách gọi đồng bộ hoặc publisher.
10. **$match, index, explain và phạm vi báo cáo hữu hạn** quan trọng hơn việc chỉ giảm số field trả về.
11. **$group không tự tạo bucket rỗng**; zero-fill cần có chính sách lịch và độ đầy đủ dữ liệu.
12. **Kiểm thử ranh giới thời gian trên MongoDB thật** giúp bảo vệ kết quả báo cáo khỏi lỗi khó quan sát khi thay đổi timezone, schema hay server version.

Hiểu rõ **biểu thức ngày giờ, múi giờ và nhóm theo thời gian** giúp dịch vụ **SPRING_DATA_MONGODB** tạo báo cáo aggregation nhất quán với lịch kinh doanh, xử lý chính xác các trường hợp DST và chuyển đổi UTC, đồng thời triển khai MongoTemplate, repository hoặc reactive access có thể kiểm thử và tối ưu hiệu năng.
