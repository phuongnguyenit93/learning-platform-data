# Garbage collection, timestamp và vòng đời cell

Một hệ thống Java ghi nhiệt độ cảm biến vào **Bigtable** mỗi phút. Mỗi lần cập nhật cùng một cột có thể tạo **phiên bản cell mới** với timestamp khác, khiến lịch sử ngày càng lớn. Nếu doanh nghiệp chỉ cần dữ liệu chi tiết trong 7 ngày và tối đa 3 phiên bản cho mỗi cột, cần kết hợp **garbage collection (GC)** để giới hạn lưu trữ và **read filters** để người dùng không nhìn thấy dữ liệu đã hết hạn nhưng chưa được thu gom vật lý.

Bài thuộc chương **Bigtable và Memorystore** trong học phần **CLOUD_PROVIDERS_GCP**. Trọng tâm là vòng đời **Bigtable cell**: tạo phiên bản, timestamp, quy tắc GC theo column family, compaction, lọc khi đọc, kiểm thử và vận hành. Phần Memorystore chỉ đối chiếu **TTL/eviction** để tránh nhầm hai cơ chế; chúng không thay thế nhau.

Sau bài này, bạn có thể:

- Giải thích cấu trúc `row key → column family → qualifier → timestamp → value` và nhiều phiên bản trong một cột.
- Phân biệt số microsecond lưu trong timestamp với **millisecond granularity mặc định** của bảng.
- Chọn `maxage`, `maxversions`, `and`, `or` theo hợp đồng giữ dữ liệu.
- Dùng `cbt` và Java client để ghi/read nhiều phiên bản, áp GC policy và read filter.
- Phân biệt **GC bất đồng bộ** với **delete do ứng dụng thực hiện**; tránh coi GC là TTL tức thì.
- Dự đoán tác động của backfill, timestamp trong tương lai, replication và thay đổi retention.
- Kiểm soát IAM, chi phí lưu trữ, hiệu năng đọc, policy drift và quyền riêng tư.

> **Môi trường lab:** chỉ thao tác trên instance/bảng thử nghiệm có dữ liệu giả, được cấp quyền và đã biết chi phí. Một GC rule chặt hơn có thể **xóa vĩnh viễn phiên bản cũ**, kể cả dữ liệu ghi trước khi đổi rule. Không thử thay chính sách trên bảng production.

## 1. Cell trong Bigtable là một phiên bản có timestamp

Bigtable là cơ sở dữ liệu **wide-column**. Dữ liệu một row gồm các **column families**; trong mỗi family có nhiều **column qualifiers**. Một giao điểm `(rowKey, family, qualifier)` có thể chứa **nhiều cells**: mỗi cell là một phiên bản `(timestamp, value)`.

~~~text
Table: telemetry
Row key: device#8a7f#20261119
├── family readings
│   ├── qualifier temperature
│   │   ├── timestamp T3  → "22.4"   (mới nhất)
│   │   ├── timestamp T2  → "21.9"
│   │   └── timestamp T1  → "21.2"   (cũ nhất)
│   └── qualifier humidity
│       ├── timestamp T2  → "62"
│       └── timestamp T1  → "64"
└── family current
    └── qualifier status
        └── timestamp T3  → "online"
~~~

**Điểm dễ nhầm:**

- `readings:temperature` có ba **cells/versions**; không phải ba columns.
- GC áp dụng **cho cả column family**, ví dụ `readings`; nhưng `maxversions=2` tính **riêng từng qualifier** trong mỗi row, không phải giữ tổng 2 cells của family.
- Hai family có thể có chính sách khác nhau: `readings` giữ lịch sử 7 ngày, `current` chỉ giữ một phiên bản.
- Row key giúp chọn vùng dữ liệu cần đọc; **GC không tự xóa cả row** theo tuổi row key, mà đánh giá cells trong family. Row không còn cells hữu ích có thể biến mất khỏi kết quả đọc.

### Phân biệt timestamp của cell với thời gian nghiệp vụ

Một cảm biến ghi dữ liệu trong ngày 10/11 nhưng gửi lên server ngày 19/11:

| Timestamp được lưu | Bigtable hiểu là | Hệ quả nếu GC `maxage=7d` |
|---|---|---|
| **10/11** (event time) | Cell đã cũ 9 ngày | Có thể đủ điều kiện GC ngay khi ghi |
| **19/11** (ingestion time) | Cell mới được tạo | Được giữ khoảng 7 ngày tính từ lúc nhận |
| **Ngày tương lai** | Cell chưa đạt giới hạn tuổi | Có thể được giữ lâu ngoài dự kiến |
| **0 hoặc timestamp giả** | Giá trị thời gian không thật | Dễ bị GC sớm hoặc giữ sai theo tuổi |

Trước khi viết policy, phải quyết định **retention tính theo event time hay ingestion time**. Nếu cần cả hai, lưu event time trong value/qualifier hoặc cấu trúc row key phù hợp, còn timestamp của cell phải có ý nghĩa thống nhất.

## 2. Đơn vị timestamp: microseconds, granularity mặc định milliseconds

Timestamp của Bigtable cell là số nguyên 64 bit, **microseconds kể từ Unix epoch UTC**. Nhưng **bảng mới mặc định dùng millisecond granularity**, nên timestamp do ứng dụng cung cấp phải **chia hết cho 1.000**.

~~~text
Millis since epoch:  1795000000123
Micros since epoch: 1795000000123000   ← hợp lệ ở bảng MILLIS
Micros since epoch: 1795000000123456   ← có thể bị từ chối ở bảng MILLIS
~~~

Với Java:

~~~java
long timestampMicros = System.currentTimeMillis() * 1_000L;
// Đơn vị micros, độ chính xác millis; chia hết 1000.
~~~

**Đừng truyền trực tiếp `System.currentTimeMillis()`** vào API đòi microseconds: sai 1.000 lần và dữ liệu có thể bị diễn giải gần năm 1970. Ngược lại, nhân `Instant.now().toEpochMilli()` với 1.000 vẫn chỉ có millisecond precision, điều này **đúng** cho bảng mặc định.

Theo tính năng hiện hành, Bigtable hỗ trợ **microsecond granularity thực sự** ở bảng được tạo với cấu hình tương ứng trên **Enterprise Plus edition**. Không mặc định mọi instance/bảng đều cho phép timestamp có 6 chữ số sau giây; kiểm tra edition, table metadata và client library trước khi dùng.

### Timestamp server/client và ghi cùng timestamp

- Không chỉ định timestamp: client library hoặc Bigtable tạo timestamp “hiện tại” theo đường ghi được hỗ trợ; thường nên dùng mặc định nếu không có yêu cầu event time.
- Chỉ định timestamp: dùng **UTC epoch microseconds** tương thích granularity; application chịu trách nhiệm clock skew, backfill và dữ liệu đến muộn.
- **Một cột tại cùng một timestamp không có lịch sử hai giá trị độc lập**: ghi đè ở cùng tuple row/family/qualifier/timestamp có thể khiến giá trị cũ không còn là phiên bản riêng. Nếu cần mỗi event phân biệt, chọn row key/qualifier phù hợp thay vì cố gắn nhiều events vào một timestamp trùng nhau.
- Nếu dùng `maxversions=1` và gửi một cell có **timestamp cũ hơn** bản mới nhất, bản ghi mới gửi có thể không xuất hiện khi đọc chỉ latest version; **thời điểm nhận request không quyết định thứ tự phiên bản**.

## 3. Vòng đời một cell: từ write tới compaction

~~~mermaid
flowchart TD
  A["Write setCell(timestamp, value)"] --> B["Cell trở thành một version có thể đọc"]
  B --> C{"Phù hợp GC policy?"}
  C -- "Chưa" --> D["Được giữ; có thể là latest hoặc lịch sử"]
  C -- "Có" --> E["Đủ điều kiện xóa, nhưng CHƯA biến mất ngay"]
  E --> F["Background compaction / garbage collection"]
  F --> G["Cell bị loại bỏ vật lý, storage giảm dần"]
  E --> H["Read filter loại cell khỏi kết quả trước GC"]
  B --> I["Application delete mutation"]
  I --> J["Không xuất hiện trong reads tiếp theo ngay"]
~~~

GC của Bigtable diễn ra **bất đồng bộ** trong nền khi compaction và có lịch hoạt động riêng; không thể yêu cầu GC chạy ngay để tiết kiệm phí. Dữ liệu đã quá tuổi hoặc quá số phiên bản vẫn có thể xuất hiện trong reads và vẫn tính phí lưu trữ **cho tới khi compaction xóa**. Thông thường cần vài ngày, đôi khi **tới một tuần**.

**Khác biệt quan trọng:** khi ứng dụng gửi **delete mutation**, cell bị xóa **không còn hiển thị ở lần đọc sau** theo semantics API, dù việc dọn vật lý vẫn có thể diễn ra sau. Với GC policy, rule **không** tự thay kết quả reads cho tới khi dữ liệu được thu gom; phải dùng read filter.

| Hành động | Kết quả đọc ngay | Thu hồi dung lượng vật lý | Dùng khi |
|---|---|---|---|
| Viết thêm version mới | Có thể đọc version mới cùng version cũ | Dung lượng tăng | Lưu lịch sử thay đổi |
| `maxversions=1` GC | Version cũ **có thể còn đọc được** | Sau compaction | Dọn lịch sử tự động |
| `maxage=7d` GC | Cell 8 ngày tuổi **có thể còn đọc được** | Sau compaction | Retention theo tuổi |
| Read filter `cellsPerColumn(1)` | Chỉ trả latest version | **Không xóa** dữ liệu | Đúng giao diện truy vấn |
| Application delete | Không còn hiển thị ở lần đọc tiếp theo | Dọn vật lý sau | Xóa chủ động theo nghiệp vụ |

**Không dùng GC đơn lẻ làm bảo đảm xóa dữ liệu đúng hạn cho yêu cầu pháp lý/bảo mật**. Cần cơ chế xóa chủ động, kiểm thử quyền truy cập và quy trình kiểm chứng/retention riêng; lưu ý backups/exports/replicas có vòng đời riêng.

## 4. GC policy được gắn vào column family

Một Bigtable table có thể có nhiều column families và **mỗi family có tối đa một biểu thức GC policy** (có thể là biểu thức kết hợp). GC không áp riêng cho một qualifier. Các loại policy cốt lõi:

| Policy | Điều kiện một cell bị đánh dấu xóa | Diễn giải |
|---|---|---|
| `maxage=7d` | Timestamp **cũ hơn** 7 ngày | Tuổi tính theo cell timestamp |
| `maxversions=3` | Cell **không thuộc 3 phiên bản mới nhất** của một cột | Mỗi row/qualifier tính riêng |
| `maxage=7d or maxversions=3` | Đủ **ít nhất một** điều kiện | Giữ **tối đa 3 phiên bản và không quá 7 ngày** |
| `maxage=7d and maxversions=3` | Đồng thời **cũ hơn 7 ngày** và **nằm ngoài 3 phiên bản mới nhất** | Giữ tối thiểu 3 phiên bản dù đã cũ; không áp hard TTL |
| Nested policy | Kết hợp các nhóm AND/OR | Dùng khi quy tắc phức tạp đã được kiểm thử |

**Quy tắc dễ nhớ:**

- **OR = xóa rộng hơn, giữ ít hơn**. Dùng khi “không quá N phiên bản **và** không quá T ngày” là yêu cầu bắt buộc.
- **AND = xóa hẹp hơn, giữ nhiều hơn**. Dùng khi muốn giữ **ít nhất N bản gần nhất**, kể cả nếu chúng già hơn T ngày.

### Minh họa tại thời điểm kiểm tra

Giả sử một cột có bốn cells theo thứ tự mới → cũ:

| Version | Tuổi | Ngoài top 2? | Cũ hơn 7 ngày? | OR: bị GC? | AND: bị GC? |
|---|---:|---|---|---|---|
| v4 | 1 ngày | Không | Không | Không | Không |
| v3 | 9 ngày | Không | Có | **Có** | Không |
| v2 | 10 ngày | Có | Có | **Có** | **Có** |
| v1 | 12 ngày | Có | Có | **Có** | **Có** |

Khác biệt lộ rõ khi **ít writes**: chỉ có một version v1 tuổi 30 ngày, policy `maxage=7d or maxversions=2` đánh dấu **xóa**, còn `maxage=7d and maxversions=2` vẫn **giữ bản duy nhất đó**. Vì vậy không viết “AND giới hạn data đúng 7 ngày” trong tài liệu vận hành.

Ở bảng trên, **v3** thuộc hai bản mới nhất dù đã 9 ngày tuổi: **OR xóa v3**, còn **AND giữ v3**. Một cell vẫn có thể bị xóa theo `maxversions` dù còn mới 1 ngày nếu trong thời gian đó có nhiều phiên bản mới hơn.

### Defaults không phải lúc nào cũng giống nhau

Một lưu ý quan trọng khi migration:

- Column family tạo bằng **HBase Java client/HBase shell** mặc định thường giữ **1 version**, theo tập quán HBase.
- Column family tạo bằng **cbt/gcloud hoặc client không thuộc HBase** mặc định có thể **giữ không giới hạn số phiên bản** nếu chưa đặt rule; **không có default TTL**.
- Vì thế luôn kiểm tra GC policy sau khi tạo family, **không tin mặc định** theo công cụ tạo.

Một GC policy mới áp dụng **hồi tố** cho dữ liệu đã tồn tại: việc giảm `maxversions` hoặc `maxage` có thể xóa các cell cũ khi compaction diễn ra. Chính sách nới lỏng **không khôi phục** dữ liệu đã thực sự bị xóa.

## 5. Lab A — tạo column families và xem các phiên bản bằng cbt

Lab giả định đã có **Bigtable instance** với ID `bt-retention-lab`, Google Cloud SDK và công cụ `cbt`. Để giới hạn chi phí, **không tự tạo cluster production** chỉ để thử GC. Với dự án mới, yêu cầu platform team tạo instance/cluster trong region và edition phù hợp.

### Chuẩn bị và tạo table

~~~bash
PROJECT_ID="my-bigtable-lab"
INSTANCE_ID="bt-retention-lab"
TABLE_ID="telemetry-gc-lab"
ROW="device#8a7f#lab"

# Giả định gcloud + cbt đã cài và bạn được phép thao tác.
gcloud config set project "$PROJECT_ID"
gcloud services enable bigtable.googleapis.com \
  bigtableadmin.googleapis.com

cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" createtable "$TABLE_ID"
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" createfamily "$TABLE_ID" readings
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" createfamily "$TABLE_ID" current
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" ls "$TABLE_ID"
~~~

**Preflight thực tế:** kiểm tra table/family chưa tồn tại, trạng thái cluster, IAM và backup/owner trước khi tạo. `cbt` dùng quyền **Bigtable Admin API** cho thay đổi schema/GC; nếu quyền data writer mà không có admin, lệnh tạo family sẽ bị `PERMISSION_DENIED`.

### Ghi ba phiên bản với timestamp rõ ràng

Sử dụng **thời gian hiện tại của máy** theo giây, đổi sang microseconds; các mốc cách nhau 60 giây nên đảm bảo khác nhau và hợp lệ ở bảng MILLIS:

~~~bash
# Chạy trong Bash/Cloud Shell; lệnh date ở môi trường khác có thể khác.
NOW_MICROS="$(($(date +%s) * 1000000))"
OLD_MICROS="$((NOW_MICROS - 120000000))"  # 2 phút trước
MID_MICROS="$((NOW_MICROS - 60000000))"   # 1 phút trước

cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" set "$TABLE_ID" "$ROW" \
  "readings:temperature=21.2@$OLD_MICROS"
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" set "$TABLE_ID" "$ROW" \
  "readings:temperature=21.9@$MID_MICROS"
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" set "$TABLE_ID" "$ROW" \
  "readings:temperature=22.4@$NOW_MICROS" \
  "current:status=online@$NOW_MICROS"

# Đọc row: hiển thị các phiên bản đang còn được lưu.
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" read "$TABLE_ID" \
  prefix="$ROW" count=1

# Read filter: chỉ trả hai phiên bản mới nhất mỗi qualifier.
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" read "$TABLE_ID" \
  prefix="$ROW" count=1 cells-per-column=2
~~~

Kỳ vọng, trước khi có GC/compaction, `readings:temperature` có ba versions với timestamp khác nhau; read có `cells-per-column=2` chỉ trả `22.4` và `21.9`. Dòng `current:status` không bị ảnh hưởng đến số phiên bản của `readings:temperature`.

### Đặt GC policy theo column family

~~~bash
# Lịch sử: không quá 7 ngày, không quá 3 phiên bản (OR).
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" setgcpolicy \
  "$TABLE_ID" readings maxage=7d or maxversions=3

# Trạng thái mới nhất: giữ tối đa 1 phiên bản mỗi qualifier.
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" setgcpolicy \
  "$TABLE_ID" current maxversions=1

cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" ls "$TABLE_ID"
~~~

Để thay semantics của `readings` từ **OR** sang **AND** trong **lab riêng**:

~~~bash
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" setgcpolicy \
  "$TABLE_ID" readings maxage=7d and maxversions=3
~~~

**Không đổi qua lại trên dữ liệu thật để thử:** policy có thể áp dụng hồi tố. Trước khi thay, đọc `cbt ls`, chụp policy/backup theo quy trình, xác định yêu cầu retention và thử với tập dữ liệu kiểm thử. Trong replicated instance, việc nới policy có điều kiện riêng; đừng tự thêm `force` chỉ để bỏ cảnh báo.

**Kỳ vọng quan trọng:** chạy `setgcpolicy` thành công **không khiến ngay lập tức** read mặc định chỉ còn đúng N versions. Ở ví dụ trên ba versions vẫn nằm trong giới hạn 3 và tuổi 2 phút, nên sẽ **không có cell nào đủ điều kiện xóa**; để quan sát độ trễ GC phải tạo dữ liệu cũ/thừa trên môi trường thử nghiệm và không dùng thời gian chờ vài phút làm tiêu chuẩn.

## 6. Lab B — Java ghi và đọc với bộ lọc nhất quán

Ví dụ ứng dụng Java 17+ có dependency `com.google.cloud:google-cloud-bigtable` được quản lý qua Google Cloud Libraries BOM. Lớp Java sau sử dụng **Application Default Credentials (ADC)** và client đã được xác nhận hỗ trợ `RowMutation.setCell`, `Filters` và `RowCell`.

**`GcCellLab.java`** (tạo trong project Java lab đã có Maven/Gradle):

~~~java
import com.google.cloud.bigtable.data.v2.BigtableDataClient;
import com.google.cloud.bigtable.data.v2.models.Filters;
import com.google.cloud.bigtable.data.v2.models.Row;
import com.google.cloud.bigtable.data.v2.models.RowCell;
import com.google.cloud.bigtable.data.v2.models.RowMutation;
import com.google.cloud.bigtable.data.v2.models.TableId;
import java.time.Duration;
import java.time.Instant;

public final class GcCellLab {
    private static final Filters FILTERS = Filters.FILTERS;

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "Usage: PROJECT_ID INSTANCE_ID TABLE_ID");
        }
        String project = args[0];
        String instance = args[1];
        String table = args[2];
        String rowKey = "device#8a7f#java";

        try (BigtableDataClient client =
                 BigtableDataClient.create(project, instance)) {

            // Bigtable timestamp là micros; bảng mặc định chính xác tới ms.
            long nowMicros = System.currentTimeMillis() * 1_000L;
            long minuteMicros = Duration.ofMinutes(1).toMillis() * 1_000L;

            RowMutation mutation = RowMutation.create(
                    TableId.of(table), rowKey)
                .setCell("readings", "temperature",
                         nowMicros - 2 * minuteMicros, "21.2")
                .setCell("readings", "temperature",
                         nowMicros - minuteMicros, "21.9")
                .setCell("readings", "temperature",
                         nowMicros, "22.4");
            client.mutateRow(mutation);

            // OR retention 7 ngày + 3 versions:
            // 1) Bỏ cells già hơn cutoff ngay ở thời điểm đọc.
            // 2) Chỉ giữ 3 versions mới nhất trong từng column.
            long cutoff = Instant.now().minus(Duration.ofDays(7))
                .toEpochMilli() * 1_000L;

            Filters.Filter retentionFilter = FILTERS.chain()
                .filter(FILTERS.timestamp().range().startClosed(cutoff))
                .filter(FILTERS.limit().cellsPerColumn(3));

            Row row = client.readRow(
                TableId.of(table), rowKey, retentionFilter);
            if (row == null) {
                System.out.println("No matching cells");
                return;
            }
            for (RowCell cell : row.getCells()) {
                System.out.printf("%s:%s @%d = %s%n",
                    cell.getFamily(),
                    cell.getQualifier().toStringUtf8(),
                    cell.getTimestamp(), // epoch MICROSECONDS
                    cell.getValue().toStringUtf8());
            }
        }
    }
}
~~~

Với dữ liệu mẫu, kỳ vọng ba cells của `readings:temperature` nằm trong 7 ngày và được trả về theo timestamp giảm dần. Khi thêm version thứ tư, `cellsPerColumn(3)` chỉ trả 3 bản mới nhất **ngay**, dù Bigtable chưa thực hiện compaction để xóa bản thứ tư.

**Vì sao chain này khớp policy OR?** Muốn cell hợp lệ cần cả `timestamp >= cutoff` **và** nằm trong top 3 phiên bản. Chúng ta áp **hai bộ lọc giữ lại** theo AND, tương ứng điều kiện xóa **age OR version**. Đối với policy GC **AND**, logic read filter sẽ khác: phải giữ cell khi **chưa quá tuổi OR còn thuộc top N**. Không áp nhầm filter OR-retention cho yêu cầu “luôn giữ ít nhất N bản”.

Lưu ý kỹ thuật:

- Cutoff ở code tính từ **thời điểm đọc** và có đơn vị epoch **microseconds**.
- `RowMutation.setCell(... timestamp, ...)` chọn timestamp do ứng dụng cung cấp; production thường nên để hệ thống gắn timestamp hiện tại trừ khi cần event time.
- `BigtableDataClient` nên tái sử dụng trong app Java/Cloud Run/GKE thay vì tạo một client cho mỗi HTTP request.
- Lọc dữ liệu ở Bigtable Data API giúp không truyền các versions không cần thiết về Java, nhưng **không tự giảm storage**.
- Client code không thực hiện **Admin API policy update**; quyền đọc/ghi dữ liệu nên tách khỏi quyền sửa GC policy.

## 7. Timestamp nghiệp vụ, backfill và lỗi thường gặp

Việc ghi đúng dữ liệu không chỉ phụ thuộc vào GC rule. Chính **timestamp mà ứng dụng chọn** quyết định tuổi cell và thứ tự version:

| Tình huống | Rủi ro | Cách kiểm soát |
|---|---|---|
| Ghi event cũ 30 ngày vào family có `maxage=7d` | Cell có thể đủ điều kiện xóa ngay; read filter 7 ngày sẽ không hiển thị | Chọn family/table backfill khác, hoặc quản lý retention theo ingestion time |
| Producer clock chạy trước 2 ngày | Cell được giữ lâu hơn dự kiến, có thể đứng đầu danh sách latest | Đồng bộ đồng hồ, kiểm tra future timestamp và độ lệch event time |
| Hai writes dùng cùng timestamp cho cùng qualifier | Không tạo hai versions độc lập | Dùng row key/qualifier phân biệt event, hoặc đảm bảo timestamp duy nhất khi cần |
| Gửi Unix milliseconds trong field yêu cầu micros | Cell bị đưa về thời điểm lịch sử bất thường và có thể bị GC | Chuẩn hóa conversion, unit tests cho epoch |
| Dữ liệu đo cùng `temperature` nhưng gửi ngược thứ tự | Latest version theo timestamp không phải request đến cuối | Đọc theo event time hoặc thiết kế record identity/sequence riêng |
| Một family chứa cả dữ liệu 1 giờ và dữ liệu 1 năm | Không thể đặt GC khác nhau theo qualifier | **Tách column families** theo retention class |

**Đừng sử dụng Bigtable timestamp như một bộ đếm phiên bản tuyệt đối** nếu nhiều writers cùng cập nhật và business đòi thứ tự chặt; timestamp được chọn có thể trùng, chậm hoặc đến muộn. Nếu cần một identity duy nhất của event, lưu event ID/sequence trong row key, qualifier hoặc value và áp điều kiện nghiệp vụ ở lớp ứng dụng.

### Khi cần “giữ đúng bản cuối, không cần lịch sử”

Với dữ liệu chỉ cần giá trị hiện tại, `maxversions=1` giảm lưu lịch sử về dài hạn, nhưng version cũ **có thể còn đọc được** trước GC. Để xóa ngay phiên bản cũ khi ghi mới, ứng dụng có thể gửi **delete-cells rồi set-cell trong cùng row mutation** theo chiến lược được Bigtable khuyến nghị; phải hiểu tác động đến concurrency, audit và replica trước khi áp dụng. Đặc biệt, **đừng dùng timestamp 0** làm cách mặc định để “đè một cell”: nếu có `maxage`, giá trị 0 rất dễ bị xem là hết hạn.

## 8. Replication và thay đổi chính sách GC

Bigtable có thể có nhiều clusters trong cùng instance, với replication theo **app profile** và thiết kế ứng dụng. GC policy thuộc cấu trúc bảng, nhưng **thời điểm compaction không đồng nhất giữa các clusters**.

Các cảnh báo theo tài liệu hiện hành:

- **Version-based GC** có thể tạo hoạt động xóa cần **replicate sang các clusters**, làm tăng CPU khi thay/giảm số versions hoặc ghi liên tục quá nhiều phiên bản.
- **Age-based GC** thực hiện việc dọn theo tuổi trên từng cluster theo cơ chế riêng; không kết luận mọi cluster bỏ cell cùng một thời điểm.
- Giảm `maxversions` ở bảng replicated có thể mất **tới khoảng một tuần** mới đồng bộ kết quả xóa; read filters vẫn cần được dùng.
- Khi **nới retention age** trong replicated instance, có giới hạn về mức tăng (tài liệu hiện hành nêu tối đa **90 ngày cho một lần tăng**) và có thể phát sinh trạng thái các clusters giữ dữ liệu khác nhau trong thời gian chuyển tiếp.
- **Không mặc định được gỡ hẳn age-based GC rule** trên replicated table; cần xem ràng buộc chính xác của instance/API và hướng dẫn trước khi thay.

Một GC policy thắt chặt **không có rollback dữ liệu chắc chắn**: cells đã compaction xóa không thể tự xuất hiện lại chỉ vì bạn đổi policy về giá trị cũ. Trước khi sửa policy ở production:

1. Kiểm kê family, current rule, thời hạn lưu trữ bắt buộc, loại dữ liệu và cluster replication topology.
2. Kiểm thử trên bảng dữ liệu giả; xác định chính xác các versions **sẽ bị xóa theo rule mới**.
3. Dự kiến ảnh hưởng đến reads, CPU, replication backlog và lưu trữ; đánh giá backup/export có quyền bảo vệ phù hợp.
4. Review/phê duyệt thay đổi, áp theo quy trình IaC; cập nhật **read filters cùng lúc** với hợp đồng retention.
5. Theo dõi storage size, read correctness, CPU và errors sau thay đổi trong nhiều ngày, không chỉ vài phút.

Nếu phải **tăng thời hạn lưu trữ**, thay rule **trước khi dữ liệu quan trọng đủ điều kiện xóa**, giữ backup/exports nếu có yêu cầu pháp lý; retention nới lỏng không cứu được cell đã biến mất.

## 9. Memorystore TTL/eviction không giống Bigtable GC

Trong chương có cả **Memorystore**, nhưng ví dụ dưới dùng **Memorystore for Redis**, không khẳng định mọi bản/edition Redis Cluster hoặc Valkey có cấu hình giống nhau.

| Tiêu chí | **Bigtable cell GC** | **Memorystore for Redis TTL/eviction** |
|---|---|---|
| Đối tượng | Cell versions trong **column family** | **Key** trong Redis |
| Đặt thời hạn | `maxage` dựa trên cell timestamp | `EXPIRE`/`SET EX` dựa trên TTL của key |
| Giới hạn lịch sử | `maxversions=N` mỗi qualifier | Không tự quản lịch sử versions kiểu Bigtable |
| Hiệu lực truy vấn | GC **không ẩn ngay** cell đủ điều kiện; cần read filter | Key hết TTL được xử lý theo semantics Redis; không coi TTL là bảo đảm giải phóng RAM tức thì |
| Dọn vật lý | Bigtable compaction nền, có thể tới một tuần | Redis expiration và memory management |
| Eviction vì memory pressure | Không có ý nghĩa “evict phiên bản least recently used” như cache | Có **maxmemory policy** cho keys khi đầy |
| Vai trò hệ thống | Lưu trữ dữ liệu quy mô lớn với lịch sử/timestamp | Cache, session, dữ liệu tạm có thể tái tạo |

Ví dụ Redis ở **mạng thử nghiệm** (client có quyền truy cập endpoint Memorystore):

~~~redis
SET cache:device:8a7f:temperature "22.4" EX 300
TTL cache:device:8a7f:temperature
GET cache:device:8a7f:temperature
DEL cache:device:8a7f:temperature
~~~

Ở đây `EX 300` nghĩa là key hết hạn sau **300 giây**. Trong Memorystore for Redis, policy mặc định thường là `volatile-lru`: khi đạt ngưỡng bộ nhớ, Redis có thể evict **những key có TTL** theo mức dùng gần đây; key có thể biến mất trước khi TTL hết nếu memory pressure và policy cho phép. Với `noeviction`, writes có thể bị từ chối khi đầy. Cần xem `used memory`, `evicted keys`, `expired keys`, cache-hit ratio và maxmemory policy.

**Kiến trúc phù hợp:** Bigtable giữ số liệu cảm biến lịch sử theo retention 7 ngày; Memorystore giữ **latest temperature** trong Redis TTL 5 phút để phục vụ dashboard nhanh. Cache miss thì đọc Bigtable bằng filter đúng retention rồi nạp lại cache. **Không dùng Memorystore làm bản duy nhất của dữ liệu telemetry cần đối soát**.

## 10. IAM, bảo mật, giám sát và chi phí

### Tách danh tính data plane và admin plane

| Danh tính | Nhiệm vụ | Quyền tối thiểu tham khảo |
|---|---|---|
| Java Cloud Run/GKE writer | Ghi cells `readings`/`current` | Bigtable user/data writer phù hợp; kiểm soát bảng và ứng dụng |
| Java reader/dashboard | Đọc cells có filter | Bigtable reader hoặc authorized view đúng phạm vi |
| Platform/DB admin | Tạo bảng/family, sửa GC rules | Quyền quản trị Bigtable Admin API, tách khỏi runtime |
| Auditor/SRE | Xem logs/metrics/policy metadata | Quyền xem Bigtable/Monitoring/Cloud Logging theo phân quyền |
| Memorystore consumer | Đọc/ghi cache | Quyền kết nối mạng và Redis AUTH/IAM tùy loại sản phẩm |

Ở Bigtable, IAM/quyền trên API và authorized views có thể giúp giảm bề mặt dữ liệu, **nhưng read filter trong Java không thay cơ chế access control**: một client khác có quyền đọc bảng mà không dùng filter có thể đọc dữ liệu GC-eligible vẫn còn vật lý. Nếu mục tiêu là bảo vệ PII sau hạn, phải có quy trình xóa và kiểm toán riêng.

Với Java client dùng **ADC** của Cloud Run/GKE (ví dụ Workload Identity Federation for GKE), không lưu JSON service account key trong image. Truy cập Bigtable API cần mạng/egress và IAM; chặn egress bằng NetworkPolicy/VPC có thể khiến client timeout dù được cấp role. Nên dùng TLS của client library, tránh truy cập không được phép từ project/tenant khác.

### Metrics và runbook

| Triệu chứng | Cần kiểm tra |
|---|---|
| Sau khi `setgcpolicy`, đọc vẫn thấy 5 versions thay vì 2 | GC bất đồng bộ, thiếu `cellsPerColumn(2)` trong read |
| Cell vừa backfill đã biến mất khỏi filtered read | Cell timestamp cũ hơn cutoff; policy dựa event time |
| `INVALID_ARGUMENT` khi write timestamp | Micros không chia hết 1.000 ở bảng MILLIS hoặc timestamp không hợp lệ |
| Giá trị “mới nhất” sai | Clock skew, timestamp tương lai hoặc late event gắn timestamp cũ |
| GC policy khác kỳ vọng | Sai column family, OR/AND nhầm, công cụ tạo family có default khác |
| Dung lượng storage chưa giảm | Compaction chưa hoàn tất; vẫn tính phí tới khi xóa vật lý |
| CPU/replication tăng sau giảm versions | Version-based deletion và replication traffic |
| `PERMISSION_DENIED` khi đổi GC | Runtime SA chỉ có data permission, thiếu Admin API policy quyền |
| `RESOURCE_EXHAUSTED`/latency cao | Large row, scan quá rộng, GC/update write load, CPU/network |
| Redis key bị evict trước TTL | Maxmemory policy/used memory, không liên quan Bigtable GC |

Theo dõi **Bigtable storage bytes**, CPU utilization, read/write latency, errors, Key Visualizer (row-key hotspots), table-level/cluster metrics và **chi phí lưu trữ sau compaction**. GC giảm storage **sau độ trễ**, không trực tiếp giảm read traffic nếu ứng dụng vẫn quét cả lịch sử thay vì dùng filters. Đối với replicated instances, theo dõi riêng các clusters vì CPU và compaction có thể khác nhau.

Chi phí tổng thể có thể gồm **Bigtable compute/cluster capacity, storage, backup, replication/network**, cùng Cloud Run/GKE processing, Cloud Logging/Monitoring và Memorystore instance memory nếu dùng cache. Không dự toán “GC 7 ngày thì đúng nửa đêm ngày thứ bảy storage cost biến mất”; dữ liệu đủ điều kiện xóa vẫn bị tính phí cho tới khi compaction hoàn tất.

## 11. Tình huống: telemetry và dashboard nhiệt độ

Một đội vận hành IoT có **100.000 cảm biến**, mỗi thiết bị gửi nhiệt độ 1 lần/phút. Dashboard cần latest reading nhanh; phân tích hành vi cần chi tiết 7 ngày; cảnh báo chỉ cần trạng thái hiện tại.

~~~mermaid
flowchart LR
  D["Devices"] --> I["Cloud Run / Pub/Sub ingest"]
  I --> B["Bigtable: readings (maxage=7d)"]
  I --> C["Bigtable: current (max 1 version)"]
  C --> M["Memorystore Redis TTL 5 phút"]
  M --> API["Dashboard Java API"]
  B --> Q["Analytics / kiểm tra lịch sử"]
~~~

**Thiết kế cần cân nhắc:** nếu cùng qualifier `readings:temperature` được ghi **mỗi phút** mà policy là `maxversions=3 or maxage=7d`, dữ liệu chỉ giữ **3 phút gần nhất** (về dài hạn), **không phải 7 ngày chi tiết**. Đó là lỗi rất thường gặp khi dùng GC version limit trên time-series.

Để thật sự giữ 7 ngày lịch sử phút, hai phương án tốt hơn:

1. **Một row theo thiết bị/ngày, qualifier theo thời điểm hoặc sample ID**, với mỗi qualifier có một cell và `maxage=7d`; cần kiểm tra kích thước row, timestamp/key design và giới hạn số qualifiers.
2. **Một row theo thiết bị/time bucket**, cùng qualifier nhưng nhiều phiên bản, chỉ dùng `maxage=7d` (hoặc maxversions đủ lớn tính từ tần suất đo, có kế hoạch cho burst/backfill).

Family `current` chỉ giữ `maxversions=1`, và Redis cache `EX 300` dành cho latest data. **Không dùng Redis TTL để xóa lịch sử Bigtable**. Khi dashboard cần 7 ngày, đọc Bigtable với timestamp window theo yêu cầu nghiệp vụ và phân vùng row key tốt để tránh scan toàn bộ table.

Ví dụ tính số versions cần giữ nếu đo **mỗi phút trong 7 ngày**, không mất mẫu:

~~~text
60 readings/giờ × 24 giờ × 7 ngày = 10.080 versions / cột
~~~

Đặt `maxversions=3` là sai rõ rệt nếu mục tiêu là giữ toàn bộ chi tiết 7 ngày. Cần đánh giá thiết kế row/key, retention chính xác, memory/CPU của reads và chi phí theo số byte thực.

## 12. Checklist thiết kế và thay đổi retention

- [ ] Đã xác định retention theo **event time** hay **ingestion time**.
- [ ] Mọi producer ghi timestamp **epoch microseconds** đúng table granularity, không nhầm milliseconds.
- [ ] Đã đánh giá late events, future timestamps, clock skew và trùng timestamp.
- [ ] Column families được chia theo **nhu cầu retention tương đồng**, không đặt GC khác nhau theo qualifier.
- [ ] Biết rõ family được tạo bằng HBase hay cbt/client khác và **policy mặc định** thực tế.
- [ ] Đã kiểm chứng **OR/AND** bằng các trường hợp rất ít phiên bản và nhiều phiên bản.
- [ ] Ứng dụng **luôn dùng timestamp/versions read filters** tương thích hợp đồng dữ liệu; không đợi GC vật lý mới đúng.
- [ ] Với dữ liệu phải xóa theo thời hạn pháp lý, có quy trình delete/audit ngoài GC.
- [ ] Policy thay đổi có owner, IaC review, backup/export, canary, theo dõi replication và rollback về logic.
- [ ] Biết rằng nới GC rule **không khôi phục** các cells đã compaction xóa.
- [ ] Có metric storage bytes, CPU, replication, read latency và cost sau thay đổi.
- [ ] Không lấy TTL/eviction của Redis làm cơ chế retention cho Bigtable.
- [ ] Đã xem xét lượng versions theo tần suất ghi, row size, row-key distribution và query pattern.
- [ ] Runtime IAM tách biệt với Admin API policy permissions; không nhúng credential key vào app Java.

## 13. Bài tập thực hành và kiểm tra hiểu biết

**Bài 1 — Đếm phiên bản.** Row `device#1` có `readings:temperature` với timestamps T1/T2/T3/T4 và `readings:humidity` với T1/T2. Nếu đặt `maxversions=2`, có bao nhiêu cells **còn được giữ theo policy** của mỗi qualifier? Nếu đọc ngay sau khi đổi rule, vì sao số cells thực tế trả về có thể nhiều hơn?

**Bài 2 — Đơn vị timestamp.** Java gửi `System.currentTimeMillis()` trực tiếp vào trường yêu cầu epoch microseconds. Giải thích timestamp bị diễn giải lệch thế nào. Viết phép chuyển đổi đúng và nêu vì sao bảng MILLIS có thể từ chối một timestamp microsecond không chia hết 1.000.

**Bài 3 — OR so với AND.** Một cột có versions v4 (1 ngày), v3 (9 ngày), v2 (10 ngày), v1 (12 ngày), xếp mới → cũ. Với `maxage=7d or maxversions=2`, các cells nào bị đánh dấu xóa? Với `maxage=7d and maxversions=2`, các cells nào bị đánh dấu xóa? Giải thích vì sao AND giữ v3.

**Bài 4 — Lab cbt.** Tạo `telemetry-gc-lab` với families `readings` và `current`; ghi ba timestamps và dùng `cbt read ... cells-per-column=2`. Sau đó đặt family `readings` dùng `maxage=7d or maxversions=3`. Vì sao set policy xong vẫn có thể đọc bản vượt rule nếu **không có filter**?

**Bài 5 — Java read filter.** Từ `GcCellLab`, sửa retention thành **10 ngày và tối đa 2 versions**. Thay cutoff/filter; tạo thêm một cell thứ tư. Giải thích sự khác nhau giữa lượng cells **được trả về** và **được lưu vật lý**.

**Bài 6 — Late event/backfill.** Hệ thống nhận batch dữ liệu ngày 01/11 vào ngày 19/11 nhưng chỉ giữ 7 ngày tính từ cell timestamp. Đề xuất hai phương án để còn xem lại batch trong 7 ngày kể từ ingestion mà không phá semantics event time.

**Bài 7 — Replication migration.** Bảng replicated có family với `maxversions=10`. Nhóm giảm còn 2 và tăng `maxage` từ 30 lên 120 ngày. Nêu các ràng buộc/cảnh báo về replicated GC, CPU, khả năng nới retention, thời gian quan sát và cách lập kế hoạch an toàn trước khi thay.

**Bài 8 — IoT thực tế.** 100.000 thiết bị ghi 1 mẫu/phút trong 7 ngày. Tính số samples/thiết bị trong 7 ngày. Vì sao `maxversions=3` cho cùng qualifier là sai? Thiết kế family/row key và read filter phù hợp, đồng thời cân nhắc giới hạn kích thước row.

**Bài 9 — Bigtable với Memorystore.** Dashboard cần latest temperature trong 5 phút và lịch sử 7 ngày. Chọn vị trí lưu dữ liệu bền vững và vị trí cache; viết lệnh Redis `SET ... EX 300` và giải thích vì sao key có thể biến mất trước TTL khi memory pressure.

**Bài 10 — Bảo mật và chi phí.** Một nhà phát triển cho rằng “GC đã đặt 30 ngày nên người dùng không thể đọc cell 31 ngày tuổi”. Chỉ ra vấn đề, đề xuất read filter, quyền IAM/authorized views, xóa chủ động khi có yêu cầu, dashboard theo dõi storage bytes và thời gian compaction.

## Tài liệu tham khảo chính thức

- [Bigtable garbage collection overview](https://cloud.google.com/bigtable/docs/garbage-collection) — GC chạy nền, defaults theo client, replication và thời gian xóa.
- [Configure garbage collection](https://cloud.google.com/bigtable/docs/configuring-garbage-collection) — `maxage`, `maxversions`, `and`, `or`, nested rules và cbt.
- [Bigtable data types and timestamps](https://cloud.google.com/bigtable/docs/data-types) — microseconds, millisecond granularity và giới hạn Enterprise Plus.
- [Bigtable writes](https://cloud.google.com/bigtable/docs/writes) — mutations, timestamp origin và thời điểm ghi.
- [cbt CLI reference](https://cloud.google.com/bigtable/docs/cbt-reference) — `set`, `read`, `setgcpolicy` và đọc policy.
- [Bigtable read filters](https://cloud.google.com/bigtable/docs/using-filters) — cells per column, timestamp range, chain filters.
- [Keep only the latest value](https://cloud.google.com/bigtable/docs/keep-only-latest-value) — delete-then-write và cảnh báo timestamp 0.
- [Java BigtableDataClient reference](https://cloud.google.com/java/docs/reference/google-cloud-bigtable/latest/com.google.cloud.bigtable.data.v2.BigtableDataClient) — thao tác reads/filters.
- [Java RowMutation reference](https://cloud.google.com/java/docs/reference/google-cloud-bigtable/latest/com.google.cloud.bigtable.data.v2.models.RowMutation) — `setCell` và timestamp.
- [Bigtable IAM](https://cloud.google.com/bigtable/docs/access-control) — quyền Data/Admin API.
- [Bigtable performance and scaling](https://cloud.google.com/bigtable/docs/performance) — rows lớn, versions và thiết kế đọc.
- [Bigtable pricing](https://cloud.google.com/bigtable/pricing) — compute, storage, replication và networking.
- [Memorystore for Redis — memory management](https://cloud.google.com/memorystore/docs/redis/memory-management-best-practices) — expired/evicted keys và tối ưu memory.
- [Memorystore for Redis — supported configurations](https://cloud.google.com/memorystore/docs/redis/supported-redis-configurations) — maxmemory policies.
