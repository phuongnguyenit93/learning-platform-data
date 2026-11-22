# Bổ sung dữ liệu còn thiếu (backfill) theo lô, có checkpoint và có thể chạy lại

Backfill là quá trình đi qua các document đã tồn tại để bổ sung một trường, tính lại giá trị hoặc chuẩn hóa cấu trúc dữ liệu theo yêu cầu mới. Với Spring Data MongoDB, ta có thể thực hiện backfill bằng **MongoTemplate**, tận dụng truy vấn theo khóa, cập nhật có điều kiện và một collection riêng để lưu **checkpoint** (vị trí đã xử lý an toàn).

Điểm khó không nằm ở câu lệnh cập nhật một document, mà ở việc đảm bảo tác vụ vẫn đúng khi có hàng triệu document, ứng dụng bị dừng giữa chừng, dữ liệu thay đổi trong lúc chạy hoặc cùng một lô phải thực hiện lại.

## 1. Mục tiêu và tình huống thực tế

Sau bài này, bạn có thể:

- Xác định chính xác dữ liệu cần backfill và xây dựng quy tắc bổ sung dữ liệu có thể kiểm chứng.
- Duyệt dữ liệu theo **lô giới hạn kích thước** bằng keyset pagination thay cho phân trang với skip lớn.
- Lưu checkpoint **sau khi tất cả cập nhật của lô đã hoàn tất**, rồi tiếp tục từ checkpoint khi khởi động lại.
- Thiết kế cập nhật **idempotent**: chạy lại không ghi đè giá trị đã được ứng dụng hoặc lần chạy trước tạo ra.
- Kiểm thử các tình huống lỗi, theo dõi tiến độ và đánh giá ảnh hưởng của truy vấn tới MongoDB.

**Ví dụ:** collection **users** hiện có trường **emailOptIn** (kiểu boolean) nhưng chưa có **preferences.notificationChannel**. Quy tắc nghiệp vụ đã được xác nhận:

| Dữ liệu nguồn | Giá trị cần bổ sung |
| --- | --- |
| emailOptIn = true | preferences.notificationChannel = "EMAIL" |
| emailOptIn = false | preferences.notificationChannel = "NONE" |
| emailOptIn thiếu hoặc null | Dừng và đưa document vào diện kiểm tra; không tự đoán |
| notificationChannel đã tồn tại | Giữ nguyên, kể cả khi khác giá trị mặc định |

Một document trước và sau khi backfill:

~~~json
// Trước
{
  "_id": {"$oid": "671000000000000000000001"},
  "emailOptIn": true,
  "preferences": {"language": "vi"}
}

// Sau
{
  "_id": {"$oid": "671000000000000000000001"},
  "emailOptIn": true,
  "preferences": {
    "language": "vi",
    "notificationChannel": "EMAIL"
  }
}
~~~

Ví dụ giả định **_id** của users là **ObjectId**, **emailOptIn** có mặt và không thay đổi trong quá trình chạy, còn **preferences** là object hoặc chưa tồn tại. Nếu thực tế có **preferences: null**, chuỗi hoặc mảng, phải xử lý dữ liệu bất thường trước khi dùng phép cập nhật trường lồng nhau. Nếu nguồn **emailOptIn** có thể thay đổi đồng thời, cần tính lại giá trị bằng aggregation update pipeline trên chính document tại thời điểm ghi hoặc tổ chức một đợt đối soát cuối.

## 2. Xác định tập dữ liệu và bất biến an toàn

Trước khi viết Java, đo số document thiếu trường đích và xem mẫu dữ liệu:

~~~javascript
db.users.countDocuments({
  "preferences.notificationChannel": { $exists: false }
});

db.users.find(
  { "preferences.notificationChannel": { $exists: false } },
  { _id: 1, emailOptIn: 1, preferences: 1 }
).limit(5);

db.users.countDocuments({ emailOptIn: { $exists: false } });
db.users.countDocuments({ emailOptIn: { $type: "null" } });
db.users.countDocuments({ preferences: { $type: "null" } });
~~~

**Phân biệt trường không tồn tại và trường bằng null:** điều kiện **$exists: false** chỉ chọn document thiếu đường dẫn trường; nó không chọn document đã có trường với giá trị null. Nếu nghiệp vụ muốn xử lý cả null, phải mở rộng bộ lọc và quy tắc chuyển đổi một cách có chủ đích. Không mặc nhiên coi null là thiếu vì null có thể là giá trị hợp lệ.

Các bất biến cần duy trì:

1. **Chỉ bổ sung trường còn thiếu.** Mỗi phép ghi phải tự kiểm tra lại điều kiện thiếu trường, ngay cả khi truy vấn đọc đã lọc trước đó.
2. **Một lô thành công rồi mới lưu checkpoint.** Nếu bất kỳ document nào lỗi, không tiến checkpoint qua lô đó.
3. **Cho phép lặp lại lô.** Crash giữa ghi dữ liệu và ghi checkpoint có thể khiến lô chạy lại; kết quả cuối vẫn phải đúng.
4. **Thứ tự duyệt ổn định.** Sắp tăng dần theo **_id** và chỉ lấy **_id** lớn hơn checkpoint; không dùng skip/limit để nhảy qua document đã được sửa.
5. **Giới hạn phạm vi của một đợt.** Lưu **upperBoundId** tại lần chạy đầu, chỉ xử lý các document có _id không vượt quá mốc này. Mốc này cố định biên theo khóa, không tạo snapshot giao dịch của toàn collection.

Một checkpoint có dạng:

~~~json
{
  "_id": "users_notification_channel_v1",
  "state": "RUNNING",
  "upperBoundId": {"$oid": "671fffffffffffffffffffff"},
  "lastSeenId": {"$oid": "671000000000000000000500"},
  "createdAt": {"$date": "2026-11-20T00:00:00Z"},
  "updatedAt": {"$date": "2026-11-20T00:02:00Z"}
}
~~~

**lastSeenId** đánh dấu _id cuối cùng của **lô đã xử lý xong**, không phải document cuối cùng vừa đọc. Trạng thái **DONE** biểu thị đã quét hết tập dữ liệu trong biên _id của đợt; muốn bổ sung dữ liệu xuất hiện sau đó, hãy tạo đợt mới với mã job mới hoặc thiết kế cơ chế đối soát riêng.

## 3. Thiết kế luồng backfill

~~~mermaid
flowchart TD
    A["Khởi chạy job"] --> B["Đọc hoặc tạo checkpoint"]
    B --> C{"Checkpoint DONE?"}
    C -- Có --> Z["Kết thúc"]
    C -- Không --> D["Tìm tối đa N document thiếu trường, _id > lastSeenId"]
    D --> E{"Lô rỗng?"}
    E -- Có --> F["Đánh dấu DONE"] --> Z
    E -- Không --> G["Tính giá trị và cập nhật có điều kiện từng document"]
    G --> H{"Toàn bộ lô thành công?"}
    H -- Không --> I["Ghi lỗi, dừng; giữ checkpoint"] 
    H -- Có --> J["Lưu _id cuối lô vào checkpoint"]
    J --> D
~~~

**Vì sao dùng keyset pagination?** Khi một document được bổ sung trường, nó không còn khớp điều kiện **$exists: false**. Nếu dùng **skip(500)** để lấy trang tiếp theo, các document đầu đã biến mất khỏi tập kết quả và việc bỏ qua 500 phần tử có thể làm sót dữ liệu. Thêm nữa, skip lớn khiến MongoDB phải duyệt qua nhiều kết quả không dùng đến. Duyệt theo **_id > lastSeenId** tránh phụ thuộc vào vị trí tương đối của các document.

## 4. Triển khai với Spring Data MongoDB

Đoạn mã sau minh họa một job chạy tuần tự bằng **MongoTemplate**, có thể được gọi từ công cụ vận hành hoặc một **ApplicationRunner** được bật có chủ đích. Không nên mặc định chạy migration tốn tài nguyên trên mọi instance mỗi lần ứng dụng khởi động.

~~~java
package example.migration;

import java.time.Instant;
import java.util.List;

import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class NotificationChannelBackfill {
    private static final String USERS = "users";
    private static final String CHECKPOINTS = "migration_checkpoints";
    private static final String JOB_ID = "users_notification_channel_v1";
    private static final String TARGET = "preferences.notificationChannel";
    private static final int BATCH_SIZE = 500;

    private final MongoTemplate mongo;

    public NotificationChannelBackfill(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public void run() {
        // Mốc biên được chụp khi job lần đầu được tạo.
        ObjectId upperBoundCandidate = findCurrentMaxId();
        if (upperBoundCandidate == null) {
            markEmptyCollectionDone();
            return;
        }

        Query checkpointKey = Query.query(Criteria.where("_id").is(JOB_ID));
        mongo.upsert(
            checkpointKey,
            new Update()
                .setOnInsert("state", "RUNNING")
                .setOnInsert("upperBoundId", upperBoundCandidate)
                .setOnInsert("createdAt", Instant.now()),
            CHECKPOINTS
        );

        Document checkpoint = mongo.findById(
            JOB_ID, Document.class, CHECKPOINTS
        );
        if (checkpoint == null) {
            throw new IllegalStateException("Cannot read migration checkpoint");
        }
        if ("DONE".equals(checkpoint.getString("state"))) {
            return;
        }
        if (!"RUNNING".equals(checkpoint.getString("state"))) {
            throw new IllegalStateException("Unexpected checkpoint state");
        }

        ObjectId upperBound = checkpoint.getObjectId("upperBoundId");
        ObjectId lastSeenId = checkpoint.getObjectId("lastSeenId");
        if (upperBound == null) {
            throw new IllegalStateException("Checkpoint has no upperBoundId");
        }

        while (true) {
            Criteria idRange = lastSeenId == null
                ? Criteria.where("_id").lte(upperBound)
                : Criteria.where("_id").gt(lastSeenId).lte(upperBound);

            Query batchQuery = Query.query(new Criteria().andOperator(
                    idRange,
                    Criteria.where(TARGET).exists(false)
                ))
                .with(Sort.by(Sort.Direction.ASC, "_id"))
                .limit(BATCH_SIZE);
            batchQuery.fields().include("_id").include("emailOptIn");

            List<Document> users = mongo.find(
                batchQuery, Document.class, USERS
            );
            if (users.isEmpty()) {
                // So sánh checkpoint để tránh ghi đè tiến độ của instance khác.
                UpdateResult done = mongo.updateFirst(
                    checkpointGuard(lastSeenId),
                    new Update()
                        .set("state", "DONE")
                        .set("finishedAt", Instant.now()),
                    CHECKPOINTS
                );
                requireSingleMatch(done);
                return;
            }

            for (Document user : users) {
                ObjectId id = user.getObjectId("_id");
                Boolean emailOptIn = user.getBoolean("emailOptIn");
                if (id == null || emailOptIn == null) {
                    // Không nuốt lỗi rồi đẩy checkpoint qua document này.
                    throw new IllegalStateException(
                        "Invalid source data for user " + id
                    );
                }

                String channel = emailOptIn ? "EMAIL" : "NONE";
                Query onlyMissing = Query.query(
                    Criteria.where("_id").is(id)
                        .and(TARGET).exists(false)
                );

                // Trường vừa được ghi bởi luồng khác sẽ không bị thay thế.
                mongo.updateFirst(
                    onlyMissing,
                    new Update().set(TARGET, channel),
                    USERS
                );
            }

            ObjectId batchLastId =
                users.get(users.size() - 1).getObjectId("_id");

            // Chỉ tiến checkpoint khi tất cả lệnh cập nhật ở trên thành công.
            UpdateResult saved = mongo.updateFirst(
                checkpointGuard(lastSeenId),
                new Update()
                    .set("lastSeenId", batchLastId)
                    .set("updatedAt", Instant.now()),
                CHECKPOINTS
            );
            requireSingleMatch(saved);
            lastSeenId = batchLastId;
        }
    }

    private Query checkpointGuard(ObjectId expectedLastSeenId) {
        return Query.query(
            Criteria.where("_id").is(JOB_ID)
                .and("state").is("RUNNING")
                .and("lastSeenId").is(expectedLastSeenId)
        );
    }

    private void requireSingleMatch(UpdateResult result) {
        if (result.getMatchedCount() != 1) {
            throw new IllegalStateException(
                "Checkpoint changed concurrently; stop and retry job"
            );
        }
    }

    private ObjectId findCurrentMaxId() {
        Query query = new Query()
            .with(Sort.by(Sort.Direction.DESC, "_id"))
            .limit(1);
        query.fields().include("_id");
        Document latest = mongo.findOne(query, Document.class, USERS);
        return latest == null ? null : latest.getObjectId("_id");
    }

    private void markEmptyCollectionDone() {
        Query key = Query.query(Criteria.where("_id").is(JOB_ID));
        mongo.upsert(
            key,
            new Update()
                .setOnInsert("state", "DONE")
                .setOnInsert("finishedAt", Instant.now()),
            CHECKPOINTS
        );
        Document checkpoint = mongo.findById(
            JOB_ID, Document.class, CHECKPOINTS
        );
        if (checkpoint == null) {
            throw new IllegalStateException("Cannot read migration checkpoint");
        }
        if ("DONE".equals(checkpoint.getString("state"))) {
            return;
        }
        // Trường hợp collection bị làm rỗng sau khi job đã bắt đầu.
        if (!"RUNNING".equals(checkpoint.getString("state"))) {
            throw new IllegalStateException("Unexpected checkpoint state");
        }
        requireSingleMatch(mongo.updateFirst(
            checkpointGuard(checkpoint.getObjectId("lastSeenId")),
            new Update()
                .set("state", "DONE")
                .set("finishedAt", Instant.now()),
            CHECKPOINTS
        ));
    }
}
~~~

Trong ví dụ, **setOnInsert** chỉ khởi tạo checkpoint nếu job chưa có; restart sẽ đọc lại **upperBoundId** và **lastSeenId** đã lưu. Phép cập nhật checkpoint sử dụng điều kiện so sánh giá trị cũ (**compare-and-set**): nếu instance khác đã thay đổi checkpoint, job hiện tại dừng thay vì ghi lùi con trỏ.

Đoạn mã xử lý mỗi document bằng một **updateFirst** để dễ quan sát và xử lý lỗi. Với tải lớn, có thể dùng **BulkOperations** theo từng lô để giảm round trip, nhưng chỉ lưu checkpoint khi toàn bộ bulk được xác nhận thành công. Nếu bulk lỗi một phần, giữ nguyên checkpoint và cho chạy lại lô bằng các cập nhật có điều kiện. Độ tin cậy của checkpoint phụ thuộc vào mức xác nhận ghi; với tác vụ quan trọng cần cấu hình **write concern** phù hợp, thường là **majority**, cho cả dữ liệu và checkpoint.

Lưu ý: bộ lọc ghi trong ví dụ bảo vệ trường đích, nhưng giả định nguồn **emailOptIn** ổn định trong thời gian backfill. Nếu nguồn có thể đổi, hãy dùng pipeline update tính giá trị từ dữ liệu hiện thời trong cùng phép ghi nguyên tử, hoặc thực hiện bước đối soát sau khi kết thúc. Một lần quét theo _id cũng không phải snapshot hoàn toàn: document được chèn muộn với _id nhỏ hơn con trỏ có thể không xuất hiện trong đợt này.

## 5. Tính idempotent và ngữ nghĩa checkpoint

Giả sử lô có 500 document:

| Điểm xảy ra sự cố | Dữ liệu thực tế | Khi chạy lại |
| --- | --- | --- |
| Trước khi ghi document nào | Chưa thay đổi | Đọc lại cùng lô |
| Sau khi đã ghi 300/500 document | 300 document có trường mới, checkpoint chưa đổi | Đọc lại lô; document đã có trường không bị ghi đè |
| Sau khi ghi 500/500, trước lúc lưu checkpoint | Lô đã được bổ sung hết | Đọc lại; các document không còn khớp điều kiện thiếu trường |
| Sau khi checkpoint được lưu | Con trỏ tiến tới _id cuối lô | Tiếp tục từ _id lớn hơn |
| Có instance khác cập nhật checkpoint | Có khả năng xung đột lịch chạy | So sánh checkpoint thất bại; dừng và đọc lại trạng thái |

Các phép ghi document và ghi checkpoint **không nằm trong một giao dịch chung** ở ví dụ này. Vì vậy, mô hình đúng là **có thể xử lý ít nhất một lần**, kết hợp cập nhật idempotent để đạt kết quả cuối như mong muốn. Đừng kỳ vọng job thực thi chính xác một lần theo nghĩa tuyệt đối.

Không tự động bỏ qua document lỗi rồi lưu checkpoint, bởi việc đó có thể bỏ sót dữ liệu vĩnh viễn. Nếu muốn cho phép lỗi riêng lẻ, cần hàng đợi lỗi/dead-letter rõ ràng, lưu lý do, quy tắc retry và đối soát cho từng _id.

## 6. Chỉ mục, giới hạn tài nguyên và hiệu năng

**_id** có chỉ mục mặc định nên phù hợp với điều kiện khoảng và sắp xếp. Tuy vậy, bộ lọc trường thiếu với **$exists: false** có thể yêu cầu đọc nhiều document để xác định dữ liệu cần sửa. Chỉ mục sparse không tự giải quyết truy vấn tìm trường **không tồn tại**.

Trước khi chạy trên dữ liệu lớn, kiểm tra execution plan:

~~~javascript
db.users.find({
  _id: {
    $gt: ObjectId("671000000000000000000000"),
    $lte: ObjectId("671fffffffffffffffffffff")
  },
  "preferences.notificationChannel": { $exists: false }
}).sort({ _id: 1 }).limit(500).explain("executionStats");
~~~

Đọc **winningPlan**, **totalKeysExamined**, **totalDocsExamined** và **nReturned**. Số document phải đọc lớn hơn nhiều số trả về cho thấy quá trình quét trường thiếu tốn I/O. Nếu tập dữ liệu rất lớn, có thể chuẩn bị một cờ/queue riêng cho các document cần migration và một chỉ mục phù hợp với cờ đó; cách này phải được đo thực tế trước khi áp dụng.

Vận hành an toàn cần chú ý:

- Bắt đầu với lô nhỏ (ví dụ 100–500), tăng dần sau khi đo thời gian, CPU, I/O, replication lag và ảnh hưởng đến truy vấn người dùng.
- Chỉ đọc các trường cần tính giá trị; giới hạn số document trong bộ nhớ mỗi lô và dùng **_id** làm con trỏ.
- Chạy một job có điều phối. Compare-and-set bảo vệ checkpoint nhưng không thay thế hoàn toàn cơ chế sở hữu job/lease khi nhiều instance có thể khởi chạy.
- Hạn chế log dữ liệu cá nhân; ưu tiên log job ID, khoảng _id, số document quét, số cập nhật thành công, số lỗi và thời gian từng lô.
- Có cấu hình tạm dừng/giảm tốc độ khi hệ thống sản xuất tăng tải. Cân nhắc **maxTimeMS** cho truy vấn và retry có backoff cho lỗi tạm thời; không retry vô hạn các lỗi dữ liệu.

Nếu cần dùng **ReactiveMongoTemplate**, vẫn áp dụng cùng nguyên tắc: đọc theo lô có giới hạn, xử lý theo thứ tự bằng **concatMap** hoặc luồng được ràng buộc concurrency, đợi publisher ghi dữ liệu hoàn tất rồi mới ghi checkpoint. Không đưa checkpoint vào một nhánh reactive có thể hoàn thành trước các nhánh cập nhật.

## 7. Transaction, nhiều worker và thay đổi dữ liệu đồng thời

MongoDB đảm bảo cập nhật trên **một document** có tính nguyên tử. Khi cần gộp nhiều document và checkpoint thành một đơn vị giao dịch, Spring Data MongoDB có thể dùng **MongoTransactionManager**, nhưng MongoDB transaction yêu cầu môi trường phù hợp (replica set hoặc sharded cluster) và giao dịch dài trên một tập lớn có chi phí cao. Thực tế, backfill hàng triệu document thường phù hợp hơn với lô nhỏ, cập nhật idempotent và checkpoint bền vững.

Nếu muốn mở rộng ra nhiều worker, không cho tất cả dùng chung một **lastSeenId** mà không phân vùng dữ liệu. Có thể tách thành các khoảng _id không chồng lấn, mỗi khoảng có checkpoint riêng; hoặc dùng queue với lease và điều kiện sở hữu. Mỗi worker phải có phạm vi cập nhật rõ ràng, cơ chế phục hồi lease hết hạn và điều kiện ghi tránh ghi đè thay đổi mới.

Với dữ liệu đang nhận ghi trực tiếp, nên triển khai theo kiểu **expand–migrate–contract**: ứng dụng mới hỗ trợ cả document cũ và mới; bắt đầu ghi trường mới cho mọi document mới; chạy backfill; đối soát; sau cùng mới bắt buộc trường trong logic đọc/validation. Không đổi code đọc để giả định tất cả document đã có trường khi job chưa được xác nhận hoàn tất.

## 8. Kiểm thử và đối soát kết quả

Những trường hợp cần kiểm thử tích hợp bằng **@DataMongoTest** và MongoDB thử nghiệm (có thể dùng Testcontainers):

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Document thiếu trường, emailOptIn = true/false | Trường mới được bổ sung đúng quy tắc |
| Document đã có notificationChannel = "PUSH" | Giá trị "PUSH" giữ nguyên |
| emailOptIn không hợp lệ hoặc preferences sai kiểu | Job báo lỗi, checkpoint không vượt document lỗi |
| Dừng sau vài cập nhật trong một lô, rồi chạy lại | Lô được hoàn tất, không ghi đè dữ liệu đã có |
| Chạy lần hai với checkpoint DONE | Kết thúc an toàn, không thay đổi document |
| Hai lần chạy cạnh tranh lưu cùng checkpoint | Một lần compare-and-set thất bại, không ghi lùi checkpoint |
| Có document được thêm sau khi job khởi chạy | Hiểu rõ giới hạn upperBoundId và quy trình xử lý ở đợt sau |

Sau khi job báo DONE, đối soát phần dữ liệu trong biên của đợt:

~~~javascript
const checkpoint = db.migration_checkpoints.findOne({
  _id: "users_notification_channel_v1"
});

db.users.countDocuments({
  _id: { $lte: checkpoint.upperBoundId },
  "preferences.notificationChannel": { $exists: false }
});

db.users.countDocuments({
  _id: { $lte: checkpoint.upperBoundId },
  emailOptIn: true,
  "preferences.notificationChannel": "EMAIL"
});
~~~

Giá trị đếm thiếu trường lý tưởng là **0** trong phạm vi được quản lý, với điều kiện dữ liệu nguồn hợp lệ và không có ghi đồng thời tạo lại khoảng trống. Hãy so sánh số lượng và lấy mẫu ngẫu nhiên để đối chiếu giá trị mới với quy tắc nghiệp vụ; **DONE** chỉ xác nhận vòng quét đã kết thúc, không tự bảo đảm dữ liệu chính xác nếu quy tắc nguồn sai hoặc dữ liệu đổi sau khi quét.

Để rollback, tránh chạy lệnh xóa toàn bộ trường mới: ứng dụng có thể đã ghi các giá trị hợp lệ sau khi backfill. Nếu cần phương án hoàn tác, thiết kế từ trước cách nhận diện chỉ những document được job thay đổi (ví dụ audit hoặc migration marker với điều kiện cập nhật an toàn), rồi thử quy trình phục hồi trên bản sao dữ liệu.

## 9. Checklist trước khi vận hành

1. Quy tắc tính trường mới đã được chủ sở hữu dữ liệu xác nhận; các giá trị null và dữ liệu bất thường đã được xử lý.
2. Job có ID riêng, phạm vi _id rõ ràng, batch size cấu hình được, checkpoint tồn tại bền vững.
3. Cập nhật dùng điều kiện trên document; chạy lại không ghi đè giá trị do ứng dụng tạo.
4. Kiểm thử kịch bản crash trước/sau checkpoint và khởi chạy trùng; có số liệu baseline để đối soát.
5. Đã đo query plan, tải ghi và replication lag trên một mẫu thực tế; có cách tạm dừng và khôi phục.
6. Ứng dụng vẫn đọc được cả schema cũ và mới cho tới khi migration và đối soát hoàn tất.

**Kết quả mong muốn** của một backfill an toàn không chỉ là điền đủ trường: hệ thống vẫn phục vụ bình thường, lỗi giữa chừng có thể khôi phục từ checkpoint và cùng một lô có thể chạy lại mà không làm hỏng dữ liệu.
