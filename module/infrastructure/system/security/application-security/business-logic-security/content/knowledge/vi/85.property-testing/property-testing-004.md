# Thuộc tính bảo toàn quota (Quota conservation property)

Một hệ thống có thể từ chối mọi request vượt hạn mức khi kiểm tra riêng lẻ nhưng vẫn bị lạm dụng qua chuỗi thao tác hợp lệ: giữ quota rồi hủy hai lần, xác nhận sau khi reservation đã hết hạn, gửi lại yêu cầu có tác dụng phụ hoặc hoàn trả quota vào sai kỳ. Những lỗi này làm xuất hiện quyền sử dụng mới dù người dùng không được cấp thêm.

Trong chương **Property Testing** của module Business Logic Security, thuộc tính bảo toàn quota giúp diễn đạt giới hạn nghiệp vụ thành một quan hệ có thể kiểm chứng trên nhiều trạng thái và chuỗi lệnh. Thay vì chỉ hỏi “request này có bị chặn không?”, ta hỏi: **mọi đơn vị quyền sử dụng hiện có đến từ đâu, đang nằm ở trạng thái nào và có bị tính hai lần hoặc biến mất ngoài quy tắc không?**

## 1. Mục tiêu và phạm vi

Bài học hướng đến khả năng:

- Định nghĩa quota và đơn vị đếm chính xác trước khi viết property.
- Mô hình hóa quota khả dụng, đang giữ và đã tiêu thụ.
- Sinh chuỗi thao tác hợp lệ lẫn thao tác lạm dụng để tìm phản ví dụ.
- Xây oracle độc lập với cách ứng dụng lưu counter.
- Kiểm tra idempotency, state machine, quyền theo đối tượng và ranh giới transaction.
- Mở rộng kiểm thử sang nhiều tenant, kỳ quota và các thao tác cạnh tranh.
- Thu nhỏ chuỗi lỗi thành một ví dụ hồi quy có thể giải thích.

Ví dụ xuyên suốt là quota gửi thông báo trong một kỳ. Một tenant được dùng tối đa L đơn vị; mỗi đơn vị cho phép một lần gửi theo định nghĩa nghiệp vụ. Ứng dụng có thể giữ trước nhiều đơn vị cho một lô gửi, xác nhận tiêu thụ hoặc trả phần giữ chưa dùng. Không có chuyển nhượng hay hoàn trả phần đã tiêu thụ trong mô hình cơ sở.

Đây là mô hình học tập. Quota số ghế đang sử dụng, giới hạn số request trong cửa sổ thời gian và ngân sách thanh toán có ngữ nghĩa khác nhau. Phải chọn đúng đơn vị, trạng thái và ranh giới trước khi áp dụng công thức.

## 2. Hiểu đúng điều được bảo toàn

### 2.1. Quota là một quyền sử dụng có phạm vi

Một bucket quota cần định danh đủ phạm vi, chẳng hạn:

```text
BucketKey = tenantId + subjectId + resourceType + periodId
```

Trong đó:

- `tenantId` ngăn quyền sử dụng của các tổ chức bị trộn với nhau.
- `subjectId` xác định chủ thể nhận quota nếu quota không chỉ đặt ở cấp tenant.
- `resourceType` xác định loại quyền, ví dụ gửi thông báo hoặc xuất báo cáo.
- `periodId` xác định kỳ được cấp, ví dụ một kỳ hợp đồng có ranh giới thời gian rõ.

Đơn vị quota phải nhất quán. Không cộng “số lô gửi” với “số thông báo”. Nếu một lô có 20 thông báo và cần giữ 20 đơn vị thì việc đếm reservation chỉ cho biết có một bản ghi, không cho biết đã giữ bao nhiêu quota.

Client có thể yêu cầu một quantity; server vẫn phải xác định caller, bucket được phép sử dụng và quy tắc tính quantity. Không lấy một `tenantId` tùy ý trong payload làm bằng chứng caller có quyền.

### 2.2. Ba ngăn trong mô hình cơ sở

Với một bucket có hạn mức cố định trong kỳ:

| Ký hiệu | Ý nghĩa |
|---|---|
| L | Tổng số đơn vị được cấp cho bucket trong kỳ |
| A | Số đơn vị khả dụng, có thể cấp giữ mới |
| R | Số đơn vị đang giữ trong các reservation ACTIVE |
| C | Số đơn vị đã tiêu thụ được ghi nhận |

Thuộc tính bảo toàn:

```text
A + R + C = L
A >= 0
R >= 0
C >= 0
```

Trạng thái đầu:

```text
A = L
R = 0
C = 0
```

Giữ q đơn vị chuyển q từ A sang R. Xác nhận chuyển q từ R sang C. Hủy hoặc hết hạn phần giữ chuyển q từ R về A. Những thao tác đó không tự thay đổi L.

### 2.3. Bảo toàn không đồng nghĩa đúng toàn bộ nghiệp vụ

Nếu người không có quyền giữ quota của tenant khác, phương trình vẫn có thể đúng. Nếu ứng dụng vừa tăng A vừa tăng L để che một lần hoàn trả thừa, phương trình cũng có thể đúng khi oracle tin trực tiếp mọi giá trị từ ứng dụng.

Vì vậy bộ property phải phối hợp:

1. Bảo toàn số lượng trong đúng bucket.
2. Không âm và không vượt giới hạn theo chính sách.
3. Chuyển trạng thái và lượng chuyển đúng với lệnh được chấp nhận.
4. Không có hiệu lực khi lệnh bị từ chối.
5. Phân quyền và cách ly giữa các bucket.
6. Một ý định gửi lại không tạo thêm hiệu lực.
7. Số lượng đã tiêu thụ khớp với tác dụng phụ theo ranh giới đã định nghĩa.

Một dịch vụ từ chối mọi lệnh có thể giữ nguyên phương trình nhưng không đáp ứng chức năng. Cần kiểm tra cả điều kiện cho phép: lệnh reserve hợp lệ, caller có quyền, bucket mở và q không vượt A phải được chấp nhận trong kịch bản tuần tự không có lỗi hạ tầng.

## 3. State machine của reservation

Mỗi reservation trong mô hình có:

```text
reservationId
bucketKey
ownerId
quantity > 0
expiresAt
status = ACTIVE | COMMITTED | RELEASED | EXPIRED
```

Quan hệ với counter:

```text
R = tổng quantity của các reservation ACTIVE trong bucket
C = tổng quantity của các reservation COMMITTED trong bucket
```

Mô hình này không xóa bản ghi COMMITTED và không có thao tác hoàn tiêu thụ. Nếu ứng dụng có compact dữ liệu, oracle phải có nguồn lịch sử tương đương; không thể suy C chỉ từ các bản ghi còn lại sau khi đã xóa lịch sử.

### 3.1. Bảng chuyển trạng thái và lượng thay đổi

| Lệnh | Điều kiện chính | Trạng thái sau | Thay đổi A, R, C |
|---|---|---|---|
| Reserve(q) | Có quyền, q > 0, q <= A, bucket mở | Tạo ACTIVE | -q, +q, 0 |
| Commit(id) | Có quyền, ACTIVE, chưa đến hạn | COMMITTED | 0, -q, +q |
| Release(id) | Có quyền, ACTIVE | RELEASED | +q, -q, 0 |
| Expire(id) | Worker hợp lệ, ACTIVE, đã đến hạn | EXPIRED | +q, -q, 0 |
| Replay(operation) | Cùng scope, key và ý định đã áp dụng | Giữ trạng thái hiện có | 0, 0, 0 |
| Lệnh không hợp lệ | Không thỏa điều kiện của hợp đồng | Không đổi trạng thái quota | 0, 0, 0 |

Các trạng thái COMMITTED, RELEASED và EXPIRED là trạng thái cuối trong mô hình cơ sở. Cùng một reservation không vừa tiêu thụ vừa trả quota.

### 3.2. Chốt chính sách thời gian

Để oracle không mơ hồ, quy ước:

- Reservation có hiệu lực để commit khi `now < expiresAt`.
- Tại `now == expiresAt`, commit bị từ chối.
- Chỉ AdvanceTime không tự trả quota. Một reservation quá hạn vẫn được tính trong R cho đến khi thao tác Expire hoặc Release hợp lệ chuyển trạng thái.
- Worker Expire chỉ xử lý ACTIVE với `now >= expiresAt`.
- Release có thể hủy ACTIVE dù đã đến hạn; Expire đến sau không được trả thêm.

Cách này có thể tạm giữ quota của reservation đã quá hạn nhưng chưa được worker thu hồi. Đó là lựa chọn bảo thủ về khả dụng, không phải cấp thêm quota. Nếu sản phẩm yêu cầu tự thu hồi khi đọc hoặc reserve, mô hình phải mô tả thao tác thu hồi đó.

Đừng kết hợp ngầm hai cách tính: loại reservation quá hạn khỏi R ngay khi thời gian đổi, nhưng vẫn chưa cộng lại A. Khi đó chính oracle cũng làm mất quota.

## 4. Từ ví dụ cụ thể đến property tổng quát

### 4.1. Một ví dụ nhỏ để kiểm tra mô hình

Với L = 10:

| Bước | Lệnh | A | R | C |
|---|---|---:|---:|---:|
| 0 | Khởi tạo | 10 | 0 | 0 |
| 1 | Reserve X, q = 6 | 4 | 6 | 0 |
| 2 | Reserve Y, q = 3 | 1 | 9 | 0 |
| 3 | Commit X | 1 | 3 | 6 |
| 4 | Release Y | 4 | 0 | 6 |
| 5 | Release Y lần nữa, key mới | 4 | 0 | 6 |

Bước 5 phải là từ chối do trạng thái cuối hoặc kết quả no-op được hợp đồng cho phép. Nó không được cộng lại 3 đơn vị. Nếu A thành 7 thì `A + R + C = 13`, vượt quyền ban đầu.

Cần kiểm tra sau **mỗi tiền tố của chuỗi**, không chỉ ở cuối. Một lỗi tăng thừa quota ở bước 5 có thể bị một thao tác sau tiêu thụ đúng phần thừa, khiến snapshot cuối trông vô hại nếu chỉ kiểm tra `A >= 0`.

### 4.2. Property trên mọi chuỗi được sinh

Gọi M là mô hình tham chiếu, S là ứng dụng được kiểm thử, và `commands` là chuỗi lệnh có danh tính caller, scope, quantity, key và thời gian.

```text
Khởi tạo M và S từ cùng một hạn mức do fixture cấp hợp lệ.

Với từng command:
    M dự đoán kết quả theo hợp đồng.
    S thực thi command qua đường xử lý thật.
    So sánh nhóm kết quả nghiệp vụ.
    Đọc trạng thái đã commit của S.
    Kiểm tra S tương ứng với M.
    Kiểm tra bảo toàn, không âm, state machine và cách ly.
```

Không cần so sánh byte của mọi response nếu response chứa timestamp hoặc ID ngẫu nhiên. So sánh các trường có ý nghĩa như nhóm kết quả, quantity, bucket, trạng thái và định danh nghiệp vụ ổn định sau khi đã ánh xạ ID.

### 4.3. Các property bổ sung

**Idempotent effect:** thêm một bản gửi lại hợp lệ của thao tác đã áp dụng không đổi A, R, C và không tạo hiệu lực nghiệp vụ mới.

**Reject without quota effect:** lệnh sai quyền, sai bucket, quantity không hợp lệ hoặc sai trạng thái không đổi projection quota. Audit ghi nhận lần thử bị từ chối có thể tăng; vì vậy không so sánh byte toàn bộ database.

**No terminal resurrection:** reservation đã ở trạng thái cuối không quay về ACTIVE qua replay hoặc lệnh chuyển trạng thái cũ.

**Monotonic consumption:** trong mô hình không hoàn tiêu thụ, C không giảm. Nếu C giảm, cần có thao tác hợp lệ ngoài mô hình cơ sở được định nghĩa rõ.

**Scope isolation:** chuỗi thao tác chỉ được phép trên bucket X không đổi quota của bucket Y độc lập.

**Valid progress:** trong điều kiện tuần tự đủ tài nguyên, một lệnh hợp lệ phải tạo đúng chuyển trạng thái, thay vì chỉ được phép không phá phương trình.

## 5. Thiết kế oracle độc lập

Một lỗi thường gặp là tính:

```text
actualAvailable + actualReserved + actualConsumed == actualLimit
```

rồi coi đó là toàn bộ kiểm thử. Nếu cả bốn counter bị ứng dụng sửa sai theo cùng một cách, test có thể đậu.

Oracle nên lấy L từ dữ liệu cấp quota đã được fixture xác nhận. Mô hình lưu reservation theo định danh logic và tính R, C từ trạng thái, thay vì sao chép cache counter của production. A được suy từ L trừ các lượng đã phân bổ.

Nên có ít nhất hai phép đối chiếu:

```text
actualCounterReserved == tổng quantity ACTIVE từ nguồn reservation có thẩm quyền
actualCounterConsumed == tổng quantity COMMITTED hoặc ledger tiêu thụ hợp lệ

actualAvailable + modelReserved + modelConsumed == modelLimit
```

Và so sánh từng reservation với mô hình. Chỉ tổng bằng nhau có thể bỏ sót việc quota bị gán sai đối tượng.

### 5.1. Không tái dùng chính hàm production làm oracle

Nếu production dùng `calculateAvailable()` bị lỗi rồi test gọi lại hàm đó để tính expected, test có thể xác nhận lại cùng sai lầm.

Mô hình tham chiếu nên:

- Nhỏ, thuần và ưu tiên công thức minh bạch.
- Không gọi repository hoặc service của production để quyết định kết quả kỳ vọng.
- Không có cache, retry hay xử lý song song nếu đang kiểm tra chuỗi tuần tự.
- Dùng biểu diễn số đủ chính xác cho tổng của oracle.
- Ánh xạ ID mô hình sang ID ứng dụng một cách tường minh.

Nếu mô hình và ứng dụng bất đồng, phải xem cả hai; mô hình tham chiếu cũng có thể sai. Một trace ngắn và bảng chuyển trạng thái giúp phân xử theo hợp đồng nghiệp vụ.

### 5.2. Đọc snapshot nhất quán

Trong phép thử tuần tự, chờ lệnh hoàn tất và đọc từ nguồn có thẩm quyền trong một transaction đọc mới. Tránh cache cũ hoặc replica trễ làm counter và reservation đến từ hai thời điểm khác nhau.

Nếu luồng expiration chạy nền, phải kiểm soát nó hoặc đưa các tác vụ của nó vào lịch test. Không để worker ngoài mô hình sửa trạng thái rồi kết luận model sai.

Với hệ thống cập nhật counter bất đồng bộ, cần phân biệt invariant trên ledger đã commit với điều kiện hội tụ của projection. Không yêu cầu mọi bản sao đều có snapshot tức thời, cũng không dùng “eventual consistency” để bỏ qua một nguồn có thẩm quyền đã cấp quá quota.

## 6. Sinh dữ liệu theo ranh giới nghiệp vụ

Property-based testing có giá trị khi generator đi qua các vùng dễ lỗi, không chỉ sinh số ngẫu nhiên đồng đều.

### 6.1. Sinh hạn mức và quantity

Các nhóm nên xuất hiện thường xuyên:

| Giá trị | Mục đích |
|---|---|
| L = 0, 1, 2 | Dễ tạo trạng thái cạn quota và trace nhỏ |
| q = 0 hoặc âm | Kiểm tra input không hợp lệ không làm tăng A |
| q = 1 | Đơn vị nhỏ nhất |
| q = A | Dùng đúng phần còn lại |
| q = A + 1 | Vượt ranh giới một đơn vị |
| q = L hoặc L + 1 | Kiểm tra giới hạn toàn kỳ |
| q gần giới hạn kiểu số | Phát hiện overflow, conversion hoặc tổng sai |

Nếu A đã bằng giá trị lớn nhất của kiểu số, không tính `A + 1` bằng phép cộng có thể overflow trong generator. Dùng số lớn cho dữ liệu mô hình, kiểm tra miền biểu diễn rồi mới chuyển thành kiểu của API.

Quantity âm đặc biệt quan trọng: code chỉ có điều kiện `available >= quantity` có thể chấp nhận quantity âm rồi tăng quota khi trừ nó. Property phải yêu cầu q > 0 và trạng thái không đổi khi từ chối.

### 6.2. Sinh đối tượng và trạng thái đích

Chọn reservation từ nhiều nhóm:

- ACTIVE chưa hết hạn.
- ACTIVE đã đến hạn nhưng chưa được thu hồi.
- COMMITTED, RELEASED hoặc EXPIRED.
- ID chưa từng tồn tại.
- ID tồn tại nhưng thuộc caller hoặc tenant khác.

Nếu generator chỉ chọn ACTIVE hợp lệ, nó gần như không kiểm tra lạm dụng state machine. Nếu chỉ sinh ID vô nghĩa, nó lại ít khi đi tới nhánh chuyển trạng thái thật.

### 6.3. Sinh chuỗi có trạng thái

Một bộ sinh theo mô hình có thể trộn:

```text
Reserve: tạo áp lực phân bổ quota.
Commit: tiêu thụ phần đang giữ.
Release: trả phần đang giữ.
AdvanceTime: đưa reservation qua ranh giới hết hạn.
Expire: mô phỏng worker thu hồi.
Replay: lặp lại ý định đã áp dụng.
ConflictingReplay: giữ key nhưng thay trường mang ý nghĩa nghiệp vụ.
UnauthorizedCommand: dùng caller không có quyền trên đối tượng.
```

Tỷ trọng phụ thuộc mục tiêu. Quan trọng là bộ sinh có khả năng tạo chuỗi Reserve → Release → Release, Reserve → Commit → Expire, và Reserve → AdvanceTime → Expire → Commit.

Với command hợp lệ, generator có thể dùng trạng thái mô hình để chọn tiền điều kiện. Với command cố ý sai, không loại chúng bằng bộ lọc toàn cục. Cần giữ những lệnh đó để kiểm tra rằng ứng dụng từ chối mà không làm đổi quota.

## 7. Ví dụ Java: kiểm tra snapshot bằng tổng chính xác

Đoạn mã dùng Java 17 và assertion của JUnit 5. Đây là helper cho fixture tích hợp; ứng dụng phải cung cấp snapshot từ counter và nguồn reservation có thẩm quyền. Nó không thay thế model-based testing của chuỗi lệnh.

```java
import java.math.BigInteger;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

enum ReservationState {
    ACTIVE, COMMITTED, RELEASED, EXPIRED
}

record ReservationView(
        String id,
        String bucketKey,
        long quantity,
        ReservationState state) {}

record QuotaSnapshot(
        String bucketKey,
        long limit,
        long available,
        long reserved,
        long consumed,
        List<ReservationView> reservations) {}

final class QuotaAssertions {
    private static BigInteger big(long value) {
        return BigInteger.valueOf(value);
    }

    static void assertConserved(
            String expectedBucket,
            long expectedLimit,
            QuotaSnapshot snapshot) {

        assertTrue(expectedLimit >= 0, "Invalid fixture limit");
        assertEquals(expectedBucket, snapshot.bucketKey());
        assertEquals(expectedLimit, snapshot.limit(),
                "Limit must not change without an authorized grant");

        assertTrue(snapshot.available() >= 0, "Negative available");
        assertTrue(snapshot.reserved() >= 0, "Negative reserved");
        assertTrue(snapshot.consumed() >= 0, "Negative consumed");

        Set<String> ids = new HashSet<>();
        BigInteger reservedFromRows = BigInteger.ZERO;
        BigInteger consumedFromRows = BigInteger.ZERO;

        for (ReservationView reservation : snapshot.reservations()) {
            assertNotNull(reservation.id());
            assertTrue(ids.add(reservation.id()), "Duplicate reservation row");
            assertEquals(expectedBucket, reservation.bucketKey());
            assertTrue(reservation.quantity() > 0, "Invalid reservation quantity");
            assertNotNull(reservation.state());

            BigInteger quantity = big(reservation.quantity());
            switch (reservation.state()) {
                case ACTIVE -> reservedFromRows =
                        reservedFromRows.add(quantity);
                case COMMITTED -> consumedFromRows =
                        consumedFromRows.add(quantity);
                case RELEASED, EXPIRED -> {
                    // Phần giữ đã trả lại; không còn nằm trong R hoặc C.
                }
            }
        }

        assertEquals(reservedFromRows, big(snapshot.reserved()),
                "Reserved counter disagrees with reservation states");
        assertEquals(consumedFromRows, big(snapshot.consumed()),
                "Consumed counter disagrees with committed reservations");

        BigInteger accounted = big(snapshot.available())
                .add(reservedFromRows)
                .add(consumedFromRows);
        assertEquals(big(expectedLimit), accounted,
                "Quota was created or lost");
    }
}
```

Dùng `BigInteger` cho tổng trong oracle tránh trường hợp chính phép cộng của test bị overflow. Điều đó không có nghĩa API production phải dùng cùng kiểu; production có thể dùng số nguyên có giới hạn, nhưng phải từ chối hoặc xử lý an toàn trước khi phép tính vượt miền.

Danh sách reservation phải đầy đủ cho bucket của mô hình. Nếu adapter chỉ lấy trang đầu hoặc bỏ lịch sử COMMITTED, helper không còn đủ thông tin để đối chiếu. Test nên có trường hợp vượt kích thước một trang để phát hiện lỗi adapter hoặc sai giả định nguồn dữ liệu.

Snapshot cũng không được tạo bằng cách lấy `reserved = sum(ACTIVE)` ngay trong adapter rồi coi đó là counter thật. Khi production có counter riêng, cần đọc giá trị riêng đó để phát hiện bất đồng giữa counter và bản ghi.

## 8. Mô hình tham chiếu cho chuỗi lệnh

Một mô hình nhỏ có thể chỉ lưu:

```text
fixedLimit
logicalNow
bucketKey
reservations: logicalId -> quantity, deadline, owner, status
appliedOperations: operationScopeAndKey -> intentFingerprint, originalResult
```

Mô hình tính A, R, C từ các reservation, không sao chép cách production cập nhật counter. Đối với các operation đã áp dụng, lưu kết quả gốc để mô phỏng replay.

### 8.1. Chốt hợp đồng idempotency của ví dụ

Để model và ứng dụng so sánh được, bài này chọn chính sách:

1. Xác thực caller và kiểm tra quyền truy cập bucket hoặc đối tượng liên quan.
2. Xác định scope của operation và fingerprint của ý định.
3. Nếu key đã có với ý định khác, từ chối xung đột và không đổi quota.
4. Nếu key đã có với cùng ý định, trả kết quả gốc, không áp dụng lại.
5. Nếu chưa có key, kiểm tra tiền điều kiện và áp dụng lệnh hợp lệ.
6. Chỉ operation đã áp dụng được lưu trong bảng kết quả của mô hình.

Lỗi nghiệp vụ không được ghi nhớ trong chính sách ví dụ. Vì vậy một Reserve từng bị từ chối do hết quota có thể thành công sau khi quota được trả lại, nếu nó chưa có operation thành công và chính sách cho phép thử lại. Hệ thống ghi nhớ cả thất bại phải có model khác phù hợp.

Quyền truy cập kết quả được xét theo chính sách hiện tại. Không để một idempotency key đoán được trở thành cách đọc kết quả của tenant khác. Nếu sản phẩm cho phép một quyền truy cập đặc biệt vào lịch sử, phải mô tả và kiểm thử quyền đó.

Fingerprint phải bao gồm loại lệnh, bucket, đối tượng đích và quantity khi chúng mang ý nghĩa nghiệp vụ. Cùng key nhưng đổi từ Release sang Commit không được xem là replay hợp lệ.

### 8.2. Pseudocode chuyển trạng thái

```text
apply(command):
    nếu caller không có quyền:
        trả FORBIDDEN, không đổi quota

    nếu key đã có:
        nếu fingerprint khác:
            trả IDEMPOTENCY_CONFLICT, không đổi quota
        trả originalResult, không đổi quota

    xét loại command:
        Reserve(q, ttl):
            yêu cầu bucket đang mở, q > 0, ttl > 0
            yêu cầu deadline biểu diễn được và q <= available()
            tạo reservation ACTIVE thuộc đúng bucket và owner

        Commit(id):
            yêu cầu reservation tồn tại trong scope được phép
            yêu cầu status == ACTIVE và now < deadline
            chuyển thành COMMITTED

        Release(id):
            yêu cầu reservation tồn tại trong scope được phép
            yêu cầu status == ACTIVE
            chuyển thành RELEASED

        Expire(id):
            yêu cầu worker được phép xử lý bucket
            yêu cầu status == ACTIVE và now >= deadline
            chuyển thành EXPIRED

    lưu fingerprint và kết quả của operation vừa áp dụng
    trả kết quả thành công
```

Pseudocode dùng kết quả INVALID_STATE cho lệnh mới nhắm trạng thái cuối. Một API cho phép no-op có thể dùng nhóm kết quả khác, nhưng tác động quota vẫn bằng không. Hãy chuẩn hóa hợp đồng trong adapter, không nới assertion thành “kết quả gì cũng được”.

`AdvanceTime` là thao tác của harness, không phải API cho người dùng chỉnh giờ hệ thống. Nó đổi clock kiểm thử và thời gian mô hình; bản thân nó không ghi operation nghiệp vụ.

### 8.3. Vòng chạy property

```text
với mỗi seed trong tập cấu hình:
    chọn L và tạo namespace dữ liệu riêng
    model = mô hình thuần mới với L
    system = fixture tích hợp mới với cùng L
    idMap = ánh xạ ID mô hình sang ID ứng dụng

    lặp step trong ngân sách số bước:
        command = generator.next(model, random, step)
        expected = model.apply(command)
        actual = system.execute(mapIds(command, idMap))

        kiểm tra nhóm kết quả theo hợp đồng
        cập nhật idMap nếu Reserve thành công
        snapshot = system.readCommittedSnapshot()
        kiểm tra snapshot khớp model
        kiểm tra bảo toàn và các property bổ sung
        ghi command, result, logicalNow và ID vào trace

    chờ kết thúc worker thuộc fixture trước khi cleanup
```

Đây là khung thiết kế, không phải runner hoàn chỉnh. Có thể triển khai bằng thư viện property-based testing của dự án hoặc một runner sinh dữ liệu có seed. Nếu runner tự viết không có shrinking tự động, phải có bước thu nhỏ thủ công hoặc bộ giảm chuỗi riêng; không tuyên bố đã có shrinking chỉ vì dùng số ngẫu nhiên.

Mỗi seed cần fixture mới. Trong một seed, không reset trạng thái sau mỗi command vì mục tiêu là kiểm tra quan hệ giữa các bước. Giới hạn số bước, thời gian chờ và lượng dữ liệu để một phản ví dụ không làm treo pipeline.

## 9. Những chuỗi lạm dụng phải có khả năng được sinh

### 9.1. Trả lại hai lần

```text
L = 1
Reserve X, q = 1
Release X, operation K1
Release X, operation K2
```

Sau Release đầu, A = 1, R = 0, C = 0. Release thứ hai không được tăng A thành 2. Hai key khác nhau ở đây có chủ đích: idempotency của request không thay thế việc bảo vệ trạng thái reservation.

Sinh thêm biến thể replay K1. Nó cũng không có hiệu lực mới, nhưng kiểm tra một cơ chế khác: bảng kết quả idempotency.

### 9.2. Xác nhận sau khi đã trả quota

```text
Reserve X, q = 1
Release X
Reserve Y, q = 1
Commit X
```

Nếu Commit X vẫn thành công, quota có thể đã vừa cấp lại cho Y vừa tiêu thụ cho X. Kiểm tra trạng thái cuối của X và tổng R + C, không chỉ available.

### 9.3. Hết hạn và xác nhận

```text
Reserve X, q = 1, expiresAt = 10
AdvanceTime đến 10
Expire X
Commit X
```

Commit bị từ chối và quota vẫn ở A. Thử thêm thứ tự Commit trước Expire khi now = 9: Commit thành công, Expire sau đó không hoàn trả phần đã tiêu thụ.

Tại now = 10, Commit trước khi worker Expire chạy vẫn phải bị từ chối theo chính sách thời gian đã chọn. Sau đó X còn ACTIVE cho đến khi được thu hồi, không tự trở thành COMMITTED chỉ vì worker đến trễ.

### 9.4. Dùng cùng key cho ý định khác

```text
Reserve q = 1, key K
Reserve q = 2, key K
```

Lệnh thứ hai phải bị từ chối xung đột trong scope đó, kể cả lúc A còn đủ cho q = 2. Nếu ứng dụng trả kết quả cũ, test cũng cần biết đó có vi phạm hợp đồng phát hiện payload khác hay không; không tự coi mọi replay đều hợp lệ.

### 9.5. Trả quota của đối tượng không thuộc quyền

Caller A tạo reservation X. Caller B không có quyền trên X gửi Release X.

Projection quota không đổi; trạng thái X vẫn ACTIVE. Một lỗi chỉ kiểm tra “caller đã đăng nhập” có thể giúp B hủy công việc của A mà phương trình vẫn đúng. Property phân quyền bắt được điều mà conservation đơn lẻ không thấy.

## 10. Kỳ quota, bổ sung hạn mức và chuyển quota

### 10.1. Không để reservation cũ bơm quota vào kỳ mới

Một tình huống dễ sai:

1. X giữ 5 đơn vị trong kỳ P1.
2. Hệ thống bắt đầu kỳ P2 với hạn mức mới.
3. Worker xử lý X hết hạn.
4. Code cộng 5 vào bucket “hiện tại” là P2.

P2 được cấp thêm ngoài chính sách, còn P1 không được kết toán đúng. Generator nên tạo các thao tác quanh ranh giới kỳ và assertion theo **bucket gốc của reservation**.

Hai kỳ phải có định danh riêng. Nếu triển khai tái dùng một hàng counter rồi reset, phép thử vẫn cần mô hình tách kỳ để phát hiện cập nhật nhầm thế hệ dữ liệu.

Chính sách cho reservation vượt qua cuối kỳ phải rõ: cấm commit sau khi kỳ đóng, cho hoàn tất trên P1 trong thời gian gia hạn, hoặc chuyển phần giữ bằng giao dịch có ghi nhận. Không suy chính sách này chỉ từ ngày trên đồng hồ.

### 10.2. Khi hạn mức được cấp thêm hoặc thu hồi

Nếu cho phép thay đổi hạn mức, thay hằng số L bằng ngân sách hiệu lực đã được phê duyệt:

```text
EffectiveLimit = InitialGrant + tổng Grant hợp lệ - tổng Revoke hợp lệ
A + R + C = EffectiveLimit
```

Lệnh Grant hoặc Revoke phải có quyền riêng, ID chống trùng và ledger đáng tin cậy. Oracle lấy chúng từ các command đã được model chấp nhận, không tin một trường limit tự thay đổi trong snapshot.

Với mô hình không cho quota âm, Revoke d đơn vị chỉ hợp lệ khi d > 0 và d <= A. Nó giảm A và EffectiveLimit cùng d; không được lấy mất phần R hoặc C mà không có chính sách xử lý nghĩa vụ đã phát sinh.

Nếu sản phẩm cho phép hạn mức mới thấp hơn lượng đã dùng, cần mô hình overage/debt riêng. Không tiếp tục áp `A >= 0` rồi sửa test để chấp nhận mọi số âm.

### 10.3. Chuyển quota giữa hai bucket

Khi cho chuyển d từ X sang Y, tổng ngân sách của tập bucket liên quan phải giữ nguyên, nhưng ngân sách từng bucket thay đổi có ghi nhận:

```text
EffectiveLimit(X) giảm d
EffectiveLimit(Y) tăng d
```

Việc ghi nợ và ghi có cần nguyên tử hoặc có trạng thái chuyển đang xử lý được mô hình hóa. Nếu chuyển bất đồng bộ, phải tính rõ lượng đang nằm trong tài khoản trung gian; không gọi một nửa giao dịch đã hoàn tất là mất quota mà cũng không bỏ qua việc ghi có hai lần.

Các mở rộng này nên có generator và model riêng sau khi mô hình quota cố định đã rõ. Một công thức tổng toàn hệ thống không thay thế kiểm tra quyền chuyển giữa các tenant.

## 11. Đưa cạnh tranh vào property testing

Chuỗi lệnh tuần tự giúp tìm lỗi state machine, nhưng không chứng minh hai transaction đồng thời giữ được cùng invariant.

### 11.1. Hai Reserve tranh phần còn lại

Sinh A ban đầu và hai quantity dương q1, q2 sao cho từng quantity không vượt A nhưng tổng vượt A. Cho hai caller hợp lệ reserve bằng hai operation ID khác nhau.

Ví dụ L = A = 10, q1 = 6, q2 = 6. Với hợp đồng nhận nguyên quantity, chỉ tối đa một lệnh có thể thành công; không tự chia mỗi lệnh thành 5.

Sau khi mọi tác vụ kết thúc:

- Snapshot bảo toàn quota.
- Tổng quantity của các reservation được nhận không vượt phần khả dụng ban đầu.
- Tập kết quả phù hợp một thứ tự xử lý hợp lệ.
- Request thua nhận kết quả nghiệp vụ/xung đột theo hợp đồng; timeout không được tự coi là hết quota.

### 11.2. Commit tranh với Release hoặc Expire

Trên cùng reservation ACTIVE, tạo các cặp Commit/Release và Commit/Expire. Một chuyển trạng thái cuối thắng theo thời gian và chính sách hợp lệ; phía còn lại không được áp dụng delta thứ hai.

Phương trình tổng có thể chưa đủ. Ví dụ code cùng đặt trạng thái COMMITTED nhưng cũng trả q về A sẽ bị bắt bằng việc đối chiếu reservation và tổng. Nếu code sửa cả limit để che lỗi, expectedLimit từ model vẫn phải phát hiện.

### 11.3. So sánh nhiều kết quả hợp lệ

Không chạy một model tuần tự theo thứ tự submit của thread rồi buộc ứng dụng giống đúng thứ tự đó. Hai lời gọi chồng lấn có thể hợp lệ theo thứ tự khác.

Với nhóm cạnh tranh nhỏ, oracle có thể liệt kê các thứ tự tuần tự phù hợp quan hệ đã quan sát và kiểm tra có ít nhất một thứ tự khớp cả kết quả lẫn trạng thái cuối. Nếu A đã hoàn tất trước khi B được gọi, thứ tự B trước A không được dùng để giải thích.

Trong một phép thử có điểm đồng bộ, ghi rõ quan hệ nhân quả mà harness thật sự tạo được. Start gate chỉ tạo cơ hội chồng lấn, không bảo đảm cả hai đã đọc cùng A cũ.

Mọi tác vụ cần deadline và phải được thu nhận lỗi. Chỉ kiểm tra conservation sau khi đã xác định các transaction liên quan kết thúc; một request đang treo có thể commit sau snapshot.

## 12. Quota và tác dụng phụ thực tế

Mô hình C phải gắn với ranh giới nghiệp vụ được định nghĩa, không chỉ một cột tăng lên cho đẹp.

Trong ví dụ gửi thông báo, có thể chọn:

- C tăng khi hệ thống chấp nhận một công việc gửi không hủy được theo hợp đồng.
- Hoặc C tăng khi bên gửi xác nhận một hiệu lực tính phí.

Hai cách cần state machine khác nhau cho giai đoạn pending. Không trộn chúng trong cùng oracle.

Nếu dùng outbox, một operation được tiêu thụ nên có event logic tương ứng theo thiết kế. Publisher có thể giao lại cùng event nhiều lần; số lần giao mạng không đồng nhất với số quyền sử dụng đã tiêu thụ.

Các property bổ sung có thể là:

```text
mỗi operation tiêu thụ chỉ tạo một hiệu lực nghiệp vụ có định danh ổn định
operation rollback không để lại outbox đã commit cho phần tiêu thụ đó
giao lại event không tạo thêm thông báo tính phí ngoài quantity đã chấp nhận
retry sau mất phản hồi không ghi nhận thêm tiêu thụ hoặc gửi thêm ngoài chính sách
```

Nếu hệ thống ngoài không hỗ trợ chống trùng và một cuộc gọi có kết quả không rõ, conservation trong database không thể tự bảo đảm gửi đúng một lần. Test phải làm lộ trạng thái chưa xác định và cơ chế reconcile, thay vì coi một counter đúng là đã an toàn đầu cuối.

## 13. Thu nhỏ phản ví dụ để tạo kiểm thử hồi quy

Một property có thể thất bại sau hàng trăm command. Mục tiêu tiếp theo là tìm chuỗi nhỏ nhất còn thể hiện **cùng loại vi phạm nghiệp vụ**.

### 13.1. Ví dụ rút gọn lỗi hoàn quota hai lần

Trace ban đầu có nhiều reservation, nhiều lần đổi giờ và retry. Sau khi bỏ các thao tác không liên quan, còn:

```text
Initial limit: 1

1. Reserve reservation X, quantity 1, operation R1
   Expected: A=0, R=1, C=0
   Actual:   A=0, R=1, C=0

2. Release X, operation U1
   Expected: A=1, R=0, C=0
   Actual:   A=1, R=0, C=0

3. Release X, operation U2
   Expected: INVALID_STATE, A=1, R=0, C=0
   Actual:   SUCCESS,       A=2, R=0, C=0
```

Việc giữ U1 và U2 khác nhau rất quan trọng. Nếu shrinker gộp chúng thành cùng key, test có thể đi vào nhánh replay và không còn kiểm tra lỗi xử lý trạng thái cuối.

Phản ví dụ này cho thấy release đã cộng quota trước hoặc tách rời việc kiểm tra/chuyển trạng thái. Cách sửa cụ thể có thể dùng cập nhật có điều kiện và transaction; phép thử hồi quy cần giữ kỳ vọng nghiệp vụ, không buộc một cách triển khai duy nhất.

### 13.2. Các chiều có thể thu nhỏ

- Số lượng command.
- Số bucket, tenant và chủ thể, nếu lỗi không phụ thuộc cách ly.
- Hạn mức và quantity về các giá trị nhỏ như 0 hoặc 1.
- Khoảng thời gian về ngay trước, đúng hoặc ngay sau deadline.
- Số request cạnh tranh và số lần retry.
- Payload về các trường tối thiểu vẫn tạo cùng ý định hoặc xung đột cần thiết.

Thu nhỏ một chuỗi có trạng thái phải giữ quan hệ phụ thuộc. Không thể bỏ Reserve X rồi coi lỗi “không tìm thấy X” là cùng phản ví dụ của lỗi Release X hai lần. Có thể đánh giá lại chuỗi sau mỗi lần giảm và chỉ giữ biến thể còn vi phạm property mục tiêu.

Với ID do server sinh, trace cần dùng tên logic ổn định rồi ánh xạ lại khi chạy. Copy nguyên ID ngẫu nhiên từ lần thất bại sang fixture mới thường không tái hiện đúng trạng thái.

### 13.3. Seed chưa phải toàn bộ bằng chứng tái hiện

Lưu seed, cấu hình generator, phiên bản model, chuỗi command, thời gian logic, scope và kết quả từng bước. Với cạnh tranh, lưu thêm quan hệ điều phối và các mốc commit/response quan sát được.

Seed có thể tái tạo lựa chọn dữ liệu, nhưng không tự tái tạo scheduler, thứ tự khóa hay worker nền. Khi phát hiện race, chuyển nó thành lịch có điều phối phù hợp và giữ invariant trong test hồi quy riêng.

Không log token xác thực, khóa bí mật hoặc toàn bộ nội dung thông báo. Trace cần định danh logic và dữ liệu nghiệp vụ tối thiểu đủ để phân tích.

## 14. Các lỗi triển khai mà property có thể phát hiện

| Lỗi | Chuỗi hoặc dữ liệu dễ làm lộ | Property phát hiện |
|---|---|---|
| Quantity âm được chấp nhận | Reserve với q < 0 | Reject without effect, không âm, model equivalence |
| Release cộng quota trước khi kiểm tra trạng thái | Reserve → Release → Release bằng key mới | Conservation, terminal state |
| Commit quên giảm reserved | Reserve → Commit | Counter khớp reservation và conservation |
| Commit chỉ đổi counter, không đổi reservation | Reserve → Commit → Release | Model trạng thái, conservation |
| Expire hoàn cả reservation đã commit | Reserve → Commit → AdvanceTime → Expire | C không giảm, không hoàn phần đã tiêu thụ |
| Replay tạo reservation mới | Reserve K → replay K | Một hiệu lực trên cùng ý định |
| Fingerprint bỏ quantity | Reserve q1 K → Reserve q2 K | Phát hiện xung đột ý định |
| Idempotency thiếu tenant scope | Hai tenant dùng cùng chuỗi key | Scope isolation, kết quả thuộc đúng bucket |
| Hoàn quota vào kỳ hiện tại thay vì kỳ gốc | Reserve P1 → mở P2 → Expire P1 | Conservation riêng từng kỳ |
| Sửa limit để cân lại counter | Một lệnh thường làm limit đổi | Expected limit độc lập từ model |
| Overflow khi cộng reservation | Quantity lớn và tổng gần giới hạn kiểu | Tổng chính xác, miền giá trị |
| Quên xét quyền khi retry | Xung đột rồi quyền bị thu hồi | Authorization và không hiệu lực sau từ chối |
| Counter và reservation commit tách rời | Gây lỗi giữa hai lần ghi | Atomicity, snapshot khớp trạng thái |
| Worker xử lý cùng event hai lần | Giao lại hoặc hai consumer cạnh tranh | Idempotent effect, tác dụng phụ |

Một phép thử chỉ kiểm tra tổng có thể bỏ sót nhiều dòng trong bảng. Giá trị của property testing đến từ việc phối hợp các thuộc tính và chuỗi command, không phải viết một phương trình rồi lặp nhiều lần.

## 15. Tổ chức chạy và đọc kết quả

### 15.1. Tách các lớp kiểm thử

**Model và domain thuần:** chạy nhiều chuỗi ngắn để kiểm tra quy tắc chuyển trạng thái và tính toán. Clock, quyền và ID đều có thể được điều khiển rõ ràng.

**Tích hợp database:** dùng service/repository thật, transaction thật và ràng buộc tương ứng môi trường đích. Tập seed có thể nhỏ hơn nhưng cần đi qua đường ghi quota, reservation, receipt và outbox liên quan.

**Cạnh tranh và nhiều instance:** tập trung vào các nhóm lệnh cùng tranh invariant. Dùng dữ liệu sinh ở ranh giới kết hợp lịch có chủ đích; không mặc định nhiều thread sẽ luôn đi trúng cửa sổ race.

**Tác dụng phụ và phục hồi:** mô phỏng lỗi trước commit, sau commit, sau tác dụng phụ nhưng trước phản hồi, hoặc giao lại thông điệp. Oracle theo dõi cả operation và hiệu lực ngoài database.

Không cần mọi property đi qua mọi lớp. Chọn lớp có đủ thành phần để kiểm tra điều đang khẳng định.

### 15.2. Kiểm tra độ phủ của generator

Theo dõi các nhóm đã thực sự xuất hiện:

- Hạn mức bằng 0 và bằng 1.
- Reserve vừa đủ và vượt đúng một đơn vị.
- Commit, Release và Expire đã được chấp nhận ít nhất trong các kịch bản phù hợp.
- Lệnh nhắm trạng thái cuối.
- Replay cùng ý định và xung đột payload.
- Lệnh không có quyền và tham chiếu sai bucket.
- Thời gian ở đúng deadline.
- Nhiều kỳ hoặc nhiều tenant nếu property tuyên bố kiểm tra phạm vi đó.

Nếu phần lớn command bị từ chối vì ID không tồn tại, số lượt chạy cao vẫn có thể rất ít giá trị. Có thể cấu hình yêu cầu độ phủ theo nhóm để lần chạy thiếu nhánh quan trọng bị báo là chưa đủ dữ liệu kiểm thử.

### 15.3. Phân loại thất bại

- **Invariant bị phá:** có bằng chứng số lượng, trạng thái, quyền hoặc tác dụng phụ sai.
- **Hợp đồng kết quả không khớp:** cần xem ứng dụng hay model diễn giải sai chính sách.
- **Oracle hoặc adapter thiếu dữ liệu:** ví dụ chỉ đọc một trang reservation.
- **Lỗi hạ tầng:** không có database, mất kết nối hoặc tài nguyên không đủ.
- **Kịch bản chưa kết thúc:** timeout, worker còn sống hoặc operation chưa rõ kết quả.

Ba nhóm sau không được tự chuyển thành “property đậu”. Cũng không tự coi mọi lỗi hạ tầng là bằng chứng quota bị phá. Giữ trace và báo rõ điều quan sát được.

Khi test fail, không retry cả chuỗi đến khi có một lần xanh rồi bỏ kết quả cũ. Hãy lưu seed và trace đầu tiên, thu nhỏ phản ví dụ, sau đó bổ sung test cố định cho lỗi đã xác định.

## 16. Bài thực hành và checklist

### 16.1. Bài thực hành

Xây fixture cho quota xuất báo cáo với L = 5, reservation có thời hạn và ba thao tác Reserve, Commit, Release. Thêm AdvanceTime và Expire ở harness/worker kiểm thử.

Thực hiện lần lượt:

1. Viết bảng chuyển trạng thái và phương trình quota theo đúng đơn vị một lượt xuất.
2. Tạo model thuần lưu reservation, clock và các operation đã áp dụng.
3. Sinh chuỗi có cả lệnh hợp lệ, lệnh sai trạng thái, quantity không hợp lệ và caller sai quyền.
4. Sau mỗi bước, so sánh kết quả với model và kiểm tra snapshot có thẩm quyền.
5. Thêm cùng key/cùng ý định và cùng key/khác ý định.
6. Thêm tenant thứ hai với cùng chuỗi key để kiểm tra cách ly.
7. Trong bản lỗi cô lập, làm Release cộng quota khi reservation đã RELEASED; chứng minh property tìm được phản ví dụ rồi khôi phục cơ chế đúng.
8. Thu nhỏ phản ví dụ thành một test hồi quy cố định.

Phần mở rộng: sinh hai Reserve độc lập với tổng quantity vượt phần khả dụng, cho chạy cạnh tranh rồi đối chiếu với các thứ tự hợp lệ của model.

Kết quả cần có invariant, hợp đồng idempotency, chính sách hết hạn, mô tả generator, trace lỗi tối giản và nguồn dữ liệu của oracle. Chỉ có thông báo “đã chạy nhiều seed” chưa chứng minh đã kiểm tra được bảo toàn quota.

### 16.2. Checklist trước khi tin vào property

- [ ] Đơn vị quota và phạm vi bucket được định nghĩa rõ.
- [ ] L trong mô hình đến từ việc cấp quyền sử dụng hợp lệ, độc lập với counter ứng dụng.
- [ ] A, R, C không âm và tổng bằng ngân sách hiệu lực.
- [ ] R và C được đối chiếu với reservation hoặc ledger đầy đủ.
- [ ] Kiểm tra sau từng tiền tố của chuỗi, không chỉ ở snapshot cuối.
- [ ] Lệnh hợp lệ phải được chấp nhận trong điều kiện tuần tự đã nêu.
- [ ] Lệnh bị từ chối không thay đổi projection quota.
- [ ] Trạng thái cuối không thể được xử lý lại để nhận thêm quota.
- [ ] Replay không tạo hiệu lực mới; cùng key khác ý định bị xử lý theo hợp đồng.
- [ ] Caller, tenant, owner và kỳ quota được kiểm tra độc lập với phương trình tổng.
- [ ] Clock, worker hết hạn và ranh giới kỳ có thể được điều khiển trong test.
- [ ] Oracle không dùng phép cộng có thể overflow hoặc hàm tính quota của production.
- [ ] Chuỗi có ID logic, seed và đủ trace để thu nhỏ, tái hiện.
- [ ] Các phép thử cạnh tranh chỉ kết luận sau khi tác vụ liên quan kết thúc.
- [ ] Hiệu lực tại hệ thống ngoài được kiểm tra theo định nghĩa tiêu thụ thực tế.

Thuộc tính bảo toàn quota biến một giới hạn nghiệp vụ thành cách kiểm tra có hệ thống: mỗi đơn vị được cấp phải nằm ở một vị trí hợp lệ, mọi lần chuyển phải được phép và mọi yêu cầu gửi lại phải giữ nguyên hiệu lực đã có. Khi kết hợp mô hình trạng thái, kiểm tra quyền và oracle độc lập, những chuỗi lạm dụng nhỏ có thể được phát hiện trước khi trở thành cách tạo thêm quyền sử dụng trong hệ thống thật.
