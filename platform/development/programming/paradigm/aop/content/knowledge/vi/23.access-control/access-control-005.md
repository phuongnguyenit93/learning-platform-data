# Thứ tự kiểm tra quyền so với giao dịch và bộ nhớ đệm trong Aspect (AOP)

## 1. Tại sao thứ tự Advice là một vấn đề bảo mật?

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, **AOP**), nhiều Aspect có thể cùng áp dụng cho một join point: kiểm soát truy cập, quản lý giao dịch (transaction), cache, truy vết, đo thời gian và xử lý lỗi. Mỗi Aspect có thể đúng khi đứng riêng, nhưng **thứ tự kết hợp** của chúng quyết định caller thực sự quan sát điều gì.

Hãy xét lời gọi `readDocument(user, id)`. Nếu một Aspect cache trả kết quả **trước khi** Aspect kiểm tra quyền chạy, người dùng không được phép có thể nhận dữ liệu mà người có quyền đã làm nóng cache. Ngược lại, kiểm tra quyền trước khi mở transaction đôi khi tiết kiệm tài nguyên, nhưng nếu quyết định quyền phụ thuộc dữ liệu đang thay đổi, kiểm tra ngoài transaction có thể tạo khoảng trống **time-of-check to time-of-use (TOCTOU)**.

Bài học chính: **mọi đường trả dữ liệu được bảo vệ phải đi qua kiểm tra quyền hợp lệ, trong khi trạng thái và transaction được quản lý đủ nhất quán theo hợp đồng nghiệp vụ**. Không có một thứ tự duy nhất luôn đúng cho mọi API. Phải chọn dựa trên dữ liệu nào được bảo vệ, nơi lưu policy, mức nhất quán, semantics của cache và các side effect.

Bài này trình bày AOP **tổng quát**, gồm join point, pointcut, around advice, composition, proxy/weaving và cách kiểm thử. Ví dụ chạy được bằng Java 17+ dùng decorator và interface proxy-like boundary để làm rõ thứ tự thực thi; không yêu cầu thư viện AOP cụ thể.

### 1.1. Những khái niệm cần phân biệt

- **Authentication (xác thực):** xác định danh tính caller. Principal/identity phải đến từ ngữ cảnh tin cậy, không tin một tham số `userId` do client tự khai.
- **Authorization (ủy quyền/kiểm tra quyền):** xác định principal có được phép làm **hành động** trên **tài nguyên** trong **ngữ cảnh hiện tại** hay không, ví dụ `(subject, action, resource, tenant, policyVersion)`.
- **Aspect/advice:** mã thực thi tại join point; around advice có thể gọi `proceed()`, đổi exception/return, hoặc thậm chí không gọi nghiệp vụ. Do đó advice có thể tạo lỗ hổng bảo mật nếu sai thứ tự.
- **Transaction:** phạm vi nhất quán/commit/rollback do nguồn dữ liệu hỗ trợ. Một transaction của database không tự làm thao tác từ xa hay hàng đợi trở thành nguyên tử.
- **Cache:** nơi lưu tạm kết quả hoặc quyết định. **Result cache** chứa dữ liệu nghiệp vụ; **authorization-decision cache** chứa quyết định allow/deny; hai loại có khóa, TTL và yêu cầu invalidation khác nhau.
- **Policy Enforcement Point (PEP):** nơi chặn và thực thi allow/deny; **Policy Decision Point (PDP):** nơi đánh giá luật. Một Aspect có thể là PEP nhưng không nên là nguồn duy nhất bảo vệ tất cả đường truy cập đến dữ liệu quan trọng.

## 2. Đọc thứ tự advice bằng mô hình lồng nhau

Ký hiệu `A -> T -> C -> B` tương ứng **Authorization -> Transaction -> Cache -> Business**. Bên trái là lớp *ngoài* và chạy trước trên đường vào; đường ra đảo chiều.

~~~text
A.before
  T.begin
    C.lookup
      B.execute (nếu cache miss)
    C.store (nếu hợp lệ)
  T.commit/rollback
A.after
~~~

Nếu `C` trả ngay khi cache hit, các lớp **bên trong C không chạy**. Nếu thứ tự là `C -> A -> T -> B`, cache hit có thể bypass cả A và T:

~~~text
C.lookup -> HIT -> return
            |
            +-- A.check KHÔNG chạy
            +-- T.begin KHÔNG chạy
            +-- B.execute KHÔNG chạy
~~~

Nếu cache miss thì chuỗi bên trong mới chạy, gây ra hành vi khác nhau giữa “cold cache” và “warm cache”. Đây là lý do một test với cache luôn trống **không đủ** để kiểm chứng kiểm soát truy cập.

### 2.1. Advice “outside” không tự có nghĩa “an toàn”

Cho `A` ở ngoài cùng chưa đủ nếu A chỉ kiểm tra kiểu tài khoản chung hoặc bỏ qua resource/action thực tế. Ví dụ “người dùng đã đăng nhập” không phải quyết định “người dùng được xem tài liệu có mã X”. Điều kiện cấp tài nguyên (object-level authorization), tenant boundary, phạm vi trường dữ liệu và thời điểm quyền bị thu hồi đều phải được xác định.

Tương tự, nếu A kiểm tra quyền theo metadata cũ, transaction bên trong A có thể làm việc trên dữ liệu đã thay đổi. Cần chọn biện pháp nhất quán tương ứng: kiểm tra lại sau khi đọc trạng thái mới, khóa/phiên bản, ràng buộc database hoặc cùng transaction khi cần.

## 3. Các cách sắp xếp phổ biến và trade-off

| Chuỗi từ ngoài vào trong | Cache hit có qua kiểm tra quyền? | Transaction được mở khi nào? | Nhận xét |
| --- | --- | --- | --- |
| `A -> T -> C -> B` | Có | Trước cache lookup | Dễ diễn giải; cache hit vẫn tốn chi phí transaction; phải kiểm soát dữ liệu được đưa vào cache trước commit |
| `A -> C -> T -> B` | Có | Chỉ khi cache miss | Tối ưu đọc nếu A kiểm tra được quyền đúng trước cache và cache hit đáp ứng contract nhất quán |
| `T -> A -> C -> B` | Có | Trước authorization | Phù hợp khi A cần đọc cùng snapshot/lock; denial có thể khiến transaction phải kết thúc/rollback |
| `C -> A -> T -> B` | **Không bảo đảm** | Chỉ khi miss | Nguy hiểm nếu C dùng chung và cache hit trả dữ liệu cần quyền mà không kiểm tra |
| `T -> C -> A -> B` | **Không bảo đảm** | Trước cache | Mở transaction không chữa việc A bị bỏ qua khi cache hit |
| `A -> T -> B -> C` | Phụ thuộc join point | Phụ thuộc phần còn lại | Ký hiệu này chỉ hợp lý nếu C được chặn ở chỗ trả dữ liệu/thao tác rõ ràng; không áp đặt máy móc cho mọi advice |

**Không dùng bảng như công thức cứng.** Một cache chỉ chứa nội dung công khai có thể không cần kiểm tra quyền theo từng người. Một cache được phân vùng theo principal vẫn phải đối phó quyền bị thu hồi. Một transaction dài mở trước tất cả kiểm tra có thể tạo chi phí/điểm chờ lock lớn. Quyết định đúng phải xuất phát từ ranh giới bảo vệ và đặc tả API.

### 3.1. Một thứ tự thường hợp lý cho truy vấn đơn giản

Khi một tài nguyên có policy ổn định và kiểm tra quyền không cần phụ thuộc transaction nghiệp vụ:

~~~text
trusted identity / policy
         |
         v
authorization (A)
         |
         v
shared result cache (C)
         |
         +-- HIT  -> result đã được kiểm tra quyền cho caller này
         |
         +-- MISS -> transaction/read (T + B) -> cache/store -> result
~~~

Đây là kiểu `A -> C -> T -> B`. Lợi ích: mọi lần trả kết quả đều qua A và cache hit có thể không mở transaction. Điều kiện: A phải thực sự đánh giá đúng quyền cho resource và action **hiện tại**, cache không để lộ metadata nhạy cảm trước A, và nội dung cached còn hợp lệ theo contract consistency.

Nếu dữ liệu/phân quyền thay đổi cùng một giao dịch, chuyển logic quyết định phù hợp vào vùng consistency bảo đảm và cân nhắc dạng `T -> A -> C -> B` hoặc `A -> T -> A_recheck -> C -> B` theo thiết kế. Việc kiểm tra lại phải dùng nguồn trạng thái tin cậy, không chỉ một decision cache quá hạn.

## 4. Kiểm soát quyền trước cache: điều kiện tối thiểu

Một Aspect cache thường hoạt động như sau:

~~~text
lookup(key):
    nếu tồn tại cached value: trả ngay
    nếu không: gọi proceed(), lưu value, trả về
~~~

Khi cached value là dữ liệu được bảo vệ, **không thể mặc nhiên đặt cache bên ngoài A** chỉ vì lần tạo cache ban đầu đã được phép. Cho ví dụ:

1. Alice có quyền đọc `report-7`, lần đầu cache miss; advice authorization cho phép và kết quả được cache.
2. Bob không có quyền đọc `report-7`.
3. Bob gọi cùng phương thức; một cache chỉ khóa theo `report-7` hit và trả dữ liệu, nên authorization advice ở phía trong không chạy.

Đây là **cache authorization bypass**. Việc thử nghiệm chỉ kiểm tra Alice thành công và Bob bị từ chối khi cache trống sẽ bỏ sót lỗi.

### 4.1. Có nên đưa principal vào cache key?

Khóa theo `(tenant, principal, resource, action, representation)` có thể giảm nguy cơ người này hit nội dung dành cho người kia; tuy nhiên **khóa đúng không thay thế kiểm tra quyền**:

- Quyền của cùng principal có thể bị thu hồi trong khi entry còn sống.
- Principal có thể thay đổi vai trò, thuộc tính, membership hoặc session scope.
- Hai user có cùng quyền nhưng được nhìn thấy các trường dữ liệu khác nhau.
- Cache key có thể thiếu tenant hoặc version của policy, tạo đụng độ dữ liệu.
- Nguồn backend có thể cập nhật trạng thái nhạy cảm trong khi TTL chưa hết.

Với dữ liệu chỉ khác theo tenant, cần phân vùng theo tenant và kiểm tra quyền trước trả kết quả. Với dữ liệu cá nhân hóa, phải có representation/authorization scope và chính sách invalidation phù hợp. Trong hệ thống phức tạp, an toàn hơn là xem cache như **nguồn kết quả không đáng tin cho đến khi đã qua chính sách truy cập hiện tại**.

### 4.2. Cache quyền và cache nội dung là hai quyết định

**Decision cache** lưu kết quả policy như `allow(subject, action, resource, context)`. Khóa có thể cần version policy, quyền hiện tại, tenant, resource version và ngữ cảnh (chẳng hạn thời gian hiệu lực). Quyết định “allow” cũ có thể gây lộ dữ liệu sau thu hồi.

**Result cache** lưu body/DTO/fragment; khóa có thể phụ thuộc resource version, locale, representation và tenant. Nó không tự biết principal có còn quyền hay không.

Nếu một A gọi decision cache bên trong nó, vẫn phải đảm bảo decision cache có TTL/invalidation phù hợp với yêu cầu thu hồi quyền. TTL ngắn giảm cửa sổ stale chứ không bảo đảm thu hồi tức thì. Với yêu cầu thu hồi ngay, cân nhắc policy version, event invalidation đáng tin, nguồn quyết định tập trung hoặc từ chối khi không thể lấy quyết định mới theo contract.

### 4.3. Không rò metadata trước kiểm tra quyền

Ngay cả khi kết quả được từ chối, cache key, thông báo “not found” và thời gian phản hồi có thể tiết lộ tài nguyên có tồn tại hay không. Nên thống nhất semantics 403/404 tùy hợp đồng và threat model, tránh log key nhạy cảm, kiểm soát response timing nếu kênh suy luận có ý nghĩa và không phát ETag/size/metadata trước khi kiểm tra quyền.

Ở cache phân tán hoặc CDN, metadata HTTP về dữ liệu cá nhân cần `Cache-Control` thích hợp và cơ chế phân vùng/cấm shared cache theo yêu cầu. Kiểm tra quyền ở lớp ứng dụng không bảo vệ một đường phân phối cache bên ngoài mà bỏ qua ứng dụng.

## 5. Transaction mở trước hay sau Authorization?

### 5.1. Kiểm tra trước transaction giúp từ chối sớm

Nếu policy có thể xác định từ thông tin tin cậy độc lập với state giao dịch (ví dụ caller không có vai trò cần thiết), kiểm tra trước `T.begin` giúp:

- Không chiếm connection, transaction slot hoặc lock cho request bị từ chối.
- Không gọi database nghiệp vụ nếu yêu cầu chắc chắn bất hợp lệ.
- Giảm side effect vô ích, giảm tải trong tấn công quá mức và thể hiện “deny before work”.

Khi authorization fail, mã nghiệp vụ, cache và transaction bên trong **không chạy**. Đây là một đặc tính nên kiểm thử bằng counter/mock cho cả đường cache hit/miss.

### 5.2. Kiểm tra cần dữ liệu nhất quán có thể nằm trong transaction

Cho nghiệp vụ duyệt lệnh chi tiền khi người duyệt còn là thành viên của nhóm phê duyệt và lệnh vẫn ở trạng thái `PENDING`. Hai điều kiện này có thể thay đổi đồng thời.

~~~text
t0: A đọc user là approver -> allow
t1: quản trị viên thu hồi quyền
t2: transaction thực hiện approve dựa trên quyết định t0
~~~

Nếu hợp đồng đòi việc thu hồi phải có hiệu lực đối với thao tác tại `t2`, quyết định `t0` có thể không đủ. Giải pháp phụ thuộc database và consistency: đọc/chốt điều kiện ngay trong transaction với isolation phù hợp; kiểm tra version và optimistic concurrency; khóa dữ liệu khi cần; thực thi predicate ngay trong lệnh cập nhật; hoặc áp dụng cơ chế bảo vệ ở datastore có ràng buộc. **Chỉ mở transaction không tự loại bỏ TOCTOU**: mức isolation, thời điểm đọc, bản ghi khóa và hợp đồng thứ tự sự kiện mới quyết định.

Một thứ tự hợp lý có thể gồm **hai tầng**:

1. Kiểm tra sơ bộ rẻ trước khi mở transaction (authenticated, tenant hợp lệ, vai trò nền tảng).
2. Mở transaction.
3. Đọc trạng thái hiện tại và kiểm tra authorization gắn với resource/action.
4. Thực thi nghiệp vụ với ràng buộc concurrency, commit, phát side effect theo quy tắc.

Không nhất thiết phải thực hiện cùng một hàm authorization hai lần; các lớp kiểm tra có thể có vai trò khác nhau. Quan trọng là quyết định cuối cần dữ liệu đang đổi phải nhất quán với thao tác được cho phép.

### 5.3. Denial và rollback

Nếu `T` nằm ngoài A, denial xảy ra sau `begin`. Transaction adapter cần kết thúc đúng trạng thái theo hợp đồng: rollback hoặc kết thúc không commit một thay đổi nào. Không “commit bất kỳ thứ gì” chỉ vì exception đã được advice khác nuốt.

Với giao dịch đã ghi tạm và sau đó fail authorization, rollback chỉ đảo ngược những thay đổi **thực sự thuộc transaction đó**; không thể tự động đảo ngược email, HTTP request hoặc message đã phát ngoài transaction. Hệ thống phải kiểm soát các side effect và phân phối event sau commit, dùng outbox/compensation nếu cần.

Nếu audit từ chối quyền buộc phải lưu ngay cả khi transaction nghiệp vụ rollback, việc ghi audit cần phạm vi lưu trữ độc lập được thiết kế rõ, không đặt audit trong transaction sẽ rollback rồi mặc nhiên tin đã lưu thành công.

## 6. Cache trong transaction: đọc, ghi và commit

### 6.1. Không publish kết quả chưa commit

Một advice cache có thể lưu kết quả khi `proceed()` trả về, nhưng transaction bao bên ngoài vẫn có thể rollback sau thời điểm cache lưu. Nếu cached value phản ánh trạng thái chưa commit, người khác có thể đọc **phantom success** hoặc dữ liệu bị rollback.

~~~text
Transaction T.begin
  Business.update -> giá trị mới, chưa commit
  Cache.put(newValue) -> người khác có thể thấy
T.commit -> thất bại, rollback
Cache vẫn chứa newValue sai
~~~

Cần phân biệt cache value **đọc** (có thể cache từ một snapshot ổn định theo chính sách) và cache value **ghi**. Với mutation, hãy phát lệnh invalidation/update cache **sau commit thành công** hoặc dùng cache/transaction integration hỗ trợ trì hoãn publish và xử lý lỗi. Việc flush cache phải có thứ tự và cơ chế phục hồi được nêu rõ; một callback chạy “sau commit” mà bị mất do process crash vẫn cần chiến lược nhất quán cuối cùng hoặc outbox nếu hệ thống yêu cầu.

### 6.2. Cache hit bỏ qua transaction có luôn được không?

Không. Nếu operation yêu cầu consistency mạnh và đọc dữ liệu liên quan đến một trạng thái transaction hiện tại (nhất là sau mutation vừa xảy ra), cache hit có thể không đáp ứng read-your-writes hoặc mức nhất quán đã hứa. Có trường hợp API chỉ chấp nhận dữ liệu từ database trong transaction cùng snapshot.

Nếu API cho phép eventual consistency, `A -> C -> T -> B` có thể hiệu quả: cache hit qua quyền rồi trả về mà không tốn transaction. Nếu API yêu cầu snapshot cụ thể, transaction có thể phải bao cả logic chọn/đọc dữ liệu; hoặc cache phải được ràng buộc theo snapshot/version. Không chọn thứ tự chỉ vì muốn “cache nhanh nhất”.

### 6.3. Invalidation sau khi quyền hay dữ liệu thay đổi

Khi một resource đổi owner, chuyển tenant, bị xóa, sửa ACL hoặc trở thành bí mật:

- Hủy/cập nhật **decision cache** của policy liên quan, không chỉ data cache.
- Hủy/cập nhật **result cache** hoặc dùng versioned keys khi representation thay đổi.
- Không dựa vào TTL như lời hứa thu hồi tức thì nếu contract đòi thu hồi ngay.
- Tránh race: callback invalidation cũ đến sau một lần cập nhật mới có thể làm cache trở về state cũ nếu không có version/ordering.
- Nếu dùng cache nhiều cấp (local + remote + CDN), kiểm tra đường nhận thay đổi policy ở **mọi cấp**.

Một phiên cache có thể cần namespace theo policy epoch hoặc tenant version. Đây là công cụ thiết kế; việc đặt version phải dựa trên một nguồn nhất quán được quản lý, không tự sinh version độc lập trên mỗi node.

## 7. Ví dụ Java 17+: thứ tự an toàn và thứ tự gây bypass

Ví dụ dưới mô phỏng một service đọc tài liệu. Tài liệu `report` chỉ được principal `alice` đọc. Các decorator đóng vai trò **around advice**: `Authorization` kiểm tra quyền, `Transaction` mô phỏng begin/commit, `Cache` lưu nội dung theo document key, `Store` đọc dữ liệu và tự bảo vệ như một lớp phòng tuyến bổ sung.

> **Lưu ý về phạm vi:** principal dạng chuỗi và transaction in log chỉ để học thứ tự. Đây không phải cơ chế xác thực thực tế hay transaction database. Trong ứng dụng thực, principal phải được lấy từ nguồn tin cậy và kiểm tra quyền ở datastore/domain nơi thích hợp.

Lưu thành `AspectOrderDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class AspectOrderDemo {
    interface Documents {
        String read(String principal, String documentId);
    }

    static final class Policy {
        static void requireRead(String principal, String documentId) {
            if (!"alice".equals(principal)
                    || !"report".equals(documentId)) {
                throw new SecurityException("access denied");
            }
        }
    }

    static final class Store implements Documents {
        @Override
        public String read(String principal, String documentId) {
            Policy.requireRead(principal, documentId);
            System.out.println("store read");
            return "confidential";
        }
    }

    static final class Authorization implements Documents {
        private final Documents next;
        Authorization(Documents next) {
            this.next = next;
        }
        @Override
        public String read(String principal, String documentId) {
            Policy.requireRead(principal, documentId);
            System.out.println("auth allow");
            return next.read(principal, documentId);
        }
    }

    static final class Transaction implements Documents {
        private final Documents next;
        Transaction(Documents next) {
            this.next = next;
        }
        @Override
        public String read(String principal, String documentId) {
            System.out.println("tx begin");
            try {
                String result = next.read(principal, documentId);
                System.out.println("tx commit");
                return result;
            } catch (RuntimeException error) {
                System.out.println("tx rollback");
                throw error;
            }
        }
    }

    static final class Cache implements Documents {
        private final Documents next;
        private final Map<String, String> values = new HashMap<>();
        Cache(Documents next) {
            this.next = next;
        }
        @Override
        public String read(String principal, String documentId) {
            String existing = values.get(documentId);
            if (existing != null) {
                System.out.println("cache hit");
                return existing;
            }
            System.out.println("cache miss");
            String loaded = next.read(principal, documentId);
            values.put(documentId, loaded);
            return loaded;
        }
    }

    public static void main(String[] args) {
        Documents safe = new Authorization(
                new Transaction(new Cache(new Store())));

        System.out.println("SAFE:");
        System.out.println("alice=" + safe.read("alice", "report"));
        try {
            safe.read("bob", "report");
        } catch (SecurityException rejected) {
            System.out.println("bob=DENIED");
        }
        System.out.println("alice-again=" + safe.read("alice", "report"));

        // Co y chon THU TU SAI de cho thay nguy co cache bypass.
        Documents unsafe = new Cache(
                new Authorization(new Transaction(new Store())));

        System.out.println("UNSAFE:");
        System.out.println("alice=" + unsafe.read("alice", "report"));
        System.out.println("bob=" + unsafe.read("bob", "report"));
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac AspectOrderDemo.java
java AspectOrderDemo
~~~

**Stdout chính xác:**

~~~text
SAFE:
auth allow
tx begin
cache miss
store read
tx commit
alice=confidential
bob=DENIED
auth allow
tx begin
cache hit
tx commit
alice-again=confidential
UNSAFE:
cache miss
auth allow
tx begin
store read
tx commit
alice=confidential
cache hit
bob=confidential
~~~

Ở chuỗi `Authorization -> Transaction -> Cache -> Store`, Bob bị từ chối **trước** transaction và cache. Alice gọi lần hai gặp cache hit nhưng vẫn đi qua authorization, vì lớp A ở bên ngoài.

Ở chuỗi **cố ý sai** `Cache -> Authorization -> Transaction -> Store`, Alice làm nóng cache trước; khi Bob gọi cùng key, `Cache` trả `confidential` tức thì. Cả lớp `Authorization` và kiểm tra bổ sung trong `Store` đều bị bỏ qua. Đây là ví dụ học tập về một lỗ hổng thực sự: **bảo vệ domain ở phía trong cũng có thể bị bypass nếu lớp ngoài trả nội dung được bảo vệ**.

Ví dụ dùng cache chung theo `documentId` để phơi bày lỗi; không triển khai cách bố trí `UNSAFE` trong hệ thống thật. Với một bộ cache phù hợp để production, còn phải xử lý phân vùng tenant, representation, cập nhật quyền, versioning, TTL, consistency, kích thước, eviction và thread-safety.

Trong đoạn demo, `Transaction` chỉ in thông báo; nó không thể commit/rollback bản ghi của một database. Vì vậy, những dòng `tx commit`/`tx rollback` chỉ minh họa thứ tự around advice, không mô tả độ bền hay isolation thực.

## 8. Khi Authorization cần transaction hoặc cần đọc tài nguyên

Không phải policy nào cũng kiểm tra được từ principal và ID trước khi truy cập dữ liệu. Có policy như:

- User phải là owner hiện tại của tài liệu, và owner nằm trong hàng dữ liệu.
- Lệnh chỉ được sửa trong trạng thái `DRAFT`.
- Membership hoặc phân quyền phụ thuộc một bảng ACL thay đổi theo thời gian.
- Chỉ một người đang giữ lease hợp lệ mới được cập nhật.
- Hai đối tượng đang được chuyển tenant cần tuân thủ một giao dịch nhất quán.

Khi đó “check before read” không có nghĩa không được đọc metadata: **có thể cần đọc một phần dữ liệu tối thiểu trong phạm vi tin cậy để ra quyết định**, nhưng chưa được trả body/metadata được bảo vệ cho caller. Nơi đánh giá policy nên được phép truy cập dữ liệu cần thiết, kể cả khi caller chưa có quyền xem đầy đủ đối tượng.

### 8.1. Hai lớp kiểm soát trong thực tế

~~~text
Authenticate + coarse policy
            |
            v
Open transaction / establish snapshot
            |
            v
Read resource state for authorization (trusted internal read)
            |
            v
Check object-level access using current state
            |
           / \
       Deny   Allow
        |       |
    rollback   operation + cache policy + commit
~~~

Lợi ích của kiểm tra sớm: loại bỏ request chắc chắn sai mà không cấp transaction. Lợi ích của kiểm tra trong transaction: quyết định theo state liên quan đến thao tác. Tuy nhiên, chính transaction cũng không bảo đảm quyền không bị thu hồi ở nơi khác nếu policy được lưu ngoài phạm vi transaction hoặc isolation không bảo vệ predicate. Phải nêu rõ **tại mốc nào** policy được coi là hợp lệ và chấp nhận cửa sổ thu hồi quyền bao lâu.

### 8.2. Tránh TOCTOU bằng điều kiện ở thao tác ghi

Nếu hành động “approve” chỉ được phép khi `owner = actor` và `status = PENDING`, việc tách `SELECT`/`authorize` rồi `UPDATE` không điều kiện có thể bị race. Có thể cân nhắc câu lệnh cập nhật có điều kiện, optimistic version check hoặc locking phù hợp, rồi xác minh số hàng thay đổi.

Ví dụ dạng SQL khái niệm (phải điều chỉnh theo schema/engine và policy thực tế):

~~~sql
UPDATE requests
SET status = 'APPROVED',
    version = version + 1
WHERE id = :request_id
  AND owner_id = :actor_id
  AND status = 'PENDING'
  AND version = :expected_version;
~~~

Nếu cập nhật được 0 hàng, chưa thể khẳng định ngay lý do là “không tồn tại”, “không có quyền”, “trạng thái không hợp lệ” hay “xung đột phiên bản”. API cần ánh xạ trạng thái đúng mà không tiết lộ sự tồn tại của dữ liệu bị bảo vệ ngoài hợp đồng. Ví dụ SQL không thay thế kiểm tra cấp tenant/permission khác nếu nghiệp vụ đòi chúng.

## 9. Khóa cache, phân vùng tenant và quyền theo trường

### 9.1. Định nghĩa cache key theo semantics

Một cache key của result không nên chỉ lấy tham số thứ nhất của method rồi giả định mọi caller giống nhau. Cân nhắc:

- **Tenant:** nếu ID chỉ duy nhất bên trong tenant, khóa phải chứa tenant ID được xác minh.
- **Resource:** ID, version hoặc revision của đối tượng.
- **Representation:** ngôn ngữ, định dạng hoặc các field được phép hiển thị.
- **Authorization context:** nếu nội dung thực sự khác theo role/user, phân vùng theo principal/role/scope đã xác thực hoặc không cache representation đó.
- **Consistency requirement:** phiên bản đã commit, policy epoch hoặc snapshot token khi contract yêu cầu.
- **Negative result:** cache lỗi “không tồn tại”/“bị từ chối” cẩn thận vì có thể stale và có nguy cơ phân biệt sự tồn tại tài nguyên.

Không nên lưu token truy cập, mật khẩu hay dữ liệu xác thực thô vào key hoặc log. Principal/tenant lấy từ ngữ cảnh tin cậy; với principal thay đổi theo phiên, key cần quy tắc ổn định và có kiểm soát vòng đời.

### 9.2. Cache các đối tượng được lọc theo quyền

Một API tìm kiếm trả danh sách tài liệu có thể lọc theo quyền của caller. Cache toàn bộ kết quả danh sách chỉ theo query string rồi trả cho mọi người sẽ lộ danh sách. Có thể cache tập ID public/metadata không nhạy cảm và lọc theo quyền tại thời điểm trả kết quả, hoặc cache theo scope chính xác. Nếu lọc theo quyền trước rồi cache “danh sách được phép”, policy revocation và scope thay đổi vẫn yêu cầu invalidation.

Với **field-level authorization**, cùng một resource có thể trả các trường khác nhau cho từng role. Cache DTO toàn bộ rồi áp filter ngoài phải chắc chắn mọi đường serialize/export đều đi qua filter, và không để object nhạy cảm lọt vào log hay callback. Nếu một field phụ thuộc thời điểm/token, cache representation có thể cần tránh hoàn toàn.

## 10. Transaction và cache trên đường ghi

Trong command như `updateDocument`, mục tiêu không chỉ là ngăn Bob đọc nhầm mà còn ngăn một lệnh ghi chưa được phép tạo trạng thái phụ.

### 10.1. Một vòng đời an toàn hơn cho mutation

1. Xác thực caller, kiểm tra sơ bộ role/tenant.
2. Mở transaction thích hợp.
3. Đọc trạng thái resource, thực thi object-level authorization theo trạng thái nhất quán.
4. Kiểm tra invariant và concurrency; ghi dữ liệu.
5. Commit; chỉ sau commit thành công mới thông báo cache invalidation/update và external event phù hợp hợp đồng.
6. Nếu rollback, không publish kết quả/cache mới; audit từ chối hoặc sự kiện lỗi nếu bắt buộc phải có cơ chế lưu độc lập.

Nếu advice cache viết ngay khi method domain trả về nhưng outer transaction chưa commit, cache có thể chứa state không tồn tại. Nếu advice transaction chạy sau callback phát external event, rollback cũng không rút lại event đó. Xác định **điểm commit thật** và **chủ sở hữu side effect**.

### 10.2. Sau commit cũng có race

Dạng “DB commit -> invalidate cache” có khoảng thời gian cache cũ vẫn phục vụ. Nếu yêu cầu consistency nghiêm ngặt, thiết kế version/lease/fencing token, phối hợp giao thức invalidation, hoặc chọn không cache đường quan trọng. Không coi việc gọi một callback sau commit là bảo đảm tuyệt đối khi process có thể chết ở giữa.

Dùng outbox cho sự kiện cần phát đáng tin là một lựa chọn, nhưng outbox không tự xử lý cache hit bị bypass authorization: hai vấn đề khác nhau.

## 11. Bảo vệ trước side channel và lỗi ứng dụng

**Thứ tự đúng về mặt control flow** vẫn chưa chắc không rò rỉ:

- **Timing:** cache hit/miss có thể khác độ trễ. Nếu kẻ gọi trái phép có thể quan sát chênh lệch trước khi deny, chúng có thể suy luận sự tồn tại của tài nguyên.
- **Exception mapping:** một advice bọc ngoài có thể chuyển `AccessDenied` thành fallback giá trị cached, làm mất ý nghĩa từ chối.
- **Logging/audit:** không in toàn bộ resource body, ACL, token hoặc user-specific cache key để chẩn đoán một denial. Audit cần lưu đủ loại action, actor đã xác thực, kết quả và thời điểm theo quy định riêng.
- **Status code:** một số API cố tình không phân biệt 403/404 để tránh tiết lộ object existence; quy tắc này phải nhất quán ở cache hit/miss.
- **Data serialization:** không cache object nhạy cảm rồi để một serializer khác tự xuất trước bước redact.
- **Error cache:** không dùng exception cache chung theo resource ID nếu thông báo lỗi chứa nội dung riêng của một người dùng.

Nếu rate limiting đặt ngoài authorization để chặn abuse sớm, nó phải có hợp đồng key/scope riêng và không được truy xuất hay phát nội dung bảo vệ. Một giới hạn IP hoặc session ở cửa vào khác với object-level authorization của tài nguyên.

## 12. Aspect composition, pointcut và đường bypass

### 12.1. Pointcut phải áp dụng ở đúng boundary

Một advice dùng pointcut theo quy ước tên method `get*` có thể bỏ lỡ `download`, `export` hoặc lời gọi nội bộ trực tiếp; một advice quá rộng có thể chặn cả thao tác chỉ đọc metadata public và tạo overhead. Với proxy, các lời gọi không đi qua proxy (ví dụ một self-call từ đối tượng mục tiêu) có thể không kích hoạt advice; cơ chế weaving có tập join point khác và cần kiểm tra riêng.

Không để bất biến ủy quyền sống **duy nhất** trong một lớp dễ bypass. Có thể cần kiểm tra ở service/domain và cơ chế enforcement ở datastore như row-level security khi phù hợp. Chúng là lớp phòng vệ bổ sung, vẫn phải được cấu hình/kiểm thử đúng, và cache bên ngoài chúng phải được kiểm soát.

### 12.2. Xác định thứ tự advice một cách tường minh

Nhiều Aspect có thể khai báo priority/order; chi tiết thứ tự phụ thuộc cơ chế AOP. Điều quan trọng là xác nhận bằng **integration test trên thứ tự thực**, bao gồm:

- Advice nào chạy trước `proceed()` và sau `proceed()`?
- Có advice nào bỏ qua `proceed()` do cache hit, denial, circuit open hoặc fallback không?
- Có retry gọi `proceed()` nhiều lần khiến authorization/transaction chạy nhiều lần hoặc không chạy trên từng attempt không?
- Exception bị bắt/chuyển ở lớp nào? Một denial có bị một outer fallback advice nuốt không?
- Callback async có phát kết quả từ một đường không được kiểm tra quyền không?

Đặc biệt, phép đổi thứ tự `A -> C` sang `C -> A` là **thay đổi hành vi bảo mật** dù thân mã của từng Aspect không đổi. Cần review và kiểm thử như thay đổi security-sensitive.

### 12.3. Vấn đề async và streaming

Với `Future`/`CompletionStage`, quanh lời gọi trả về handle chưa chắc bảo vệ mọi lúc tạo và phát kết quả. Nếu callback hoặc worker về sau truy cập resource với context khác, phải định nghĩa quyền dùng ở **thời điểm submit** hay **thời điểm thực thi**, cách truyền principal và thời điểm recheck. Không tự động “carry” `ThreadLocal` sang thread khác.

Với stream, quyền có thể cần kiểm tra khi mở subscription và/hoặc mỗi lúc dữ liệu được phát nếu policy có thể bị thu hồi trong suốt stream. Một cache phần tử stream đặt ngoài enforcement có thể lộ dữ liệu sau khi subscriber mất quyền. Xác định hủy/close stream và data redaction đúng vòng đời.

## 13. Kiểm thử trọng tâm: cache hit, denial và isolation

Để kiểm chứng thứ tự, kiểm thử ít nhất **cùng một resource với hai principal khác quyền** và ép chuyển trạng thái từ cache miss sang hit.

| Kịch bản | Điều phải chứng minh |
| --- | --- |
| Alice được phép, cache miss | A chạy; store chỉ được gọi sau allow |
| Bob bị từ chối khi cache còn trống | Không truy xuất dữ liệu không phép; không bắt đầu mutation |
| **Alice warm cache, Bob request cùng key** | **Bob vẫn bị từ chối, cache hit không bypass A** |
| Bob bị từ chối, Alice request lại | Không poison cache; Alice nhận kết quả hợp lệ |
| Alice mất quyền sau khi cache được làm nóng | Recheck/invalidation theo hợp đồng thu hồi; không trả dữ liệu trái phép |
| Hai tenant trùng document ID | Không cross-tenant cache hit |
| Cùng user nhưng scope/representation khác | Không lộ field khác scope |
| Cache miss rồi transaction rollback | Không publish value chưa commit |
| Update thành công rồi invalidation lỗi | Hệ thống phát hiện/khôi phục theo consistency contract |
| Authorization cần mutable ACL | Đánh giá trạng thái đúng tại điểm nhất quán, tránh TOCTOU |
| Advice ngoài trả fallback | Không biến denial thành success |
| Self-call hoặc đường async bypass proxy | Policy vẫn được thực thi ở boundary đáng tin |
| Load lớn, concurrency cao | Đồng bộ cache/transaction phù hợp; không leak qua race hoặc stale context |

### 13.1. Test thứ tự chính xác

Dùng fake `Authorization`, `Transaction`, `Cache` và `Business` ghi một event log có cấu trúc. Kiểm tra các chuỗi expected cụ thể:

~~~text
DENY:
A.check -> A.deny
(khong thay T.begin, C.hit, B.execute)

ALLOW + CACHE_HIT:
A.check -> A.allow -> C.hit -> return
(khong can T.begin neu thu tu A -> C -> T -> B)

ALLOW + CACHE_MISS:
A.check -> A.allow -> C.miss -> T.begin
  -> B.execute -> T.commit -> C.publish/return
~~~

Dòng `C.publish` là **logic minh họa**: với cache result từ một read-only transaction, có thể đặt lưu cache sau khi kết quả được xác nhận. Với mutation, đợi commit/invalidation theo cơ chế riêng; không ép mọi kiểu cache dùng cùng hook.

### 13.2. Dùng concurrency test thay vì ngủ đoán chừng

TOCTOU chỉ xuất hiện khi các thao tác đan xen. Dùng `CountDownLatch`, `Phaser`, fake clock và transaction boundary được điều khiển để:

1. Tạm dừng sau khi A đọc quyền.
2. Thu hồi hoặc thay đổi quyền/tài nguyên ở một luồng khác.
3. Cho phép transaction tiếp tục.
4. Xác nhận hệ thống xử lý theo contract đã chọn: deny, retry với version mới hoặc thực thi theo một snapshot đã được chấp nhận.

Phải chỉ rõ contract về revocation và snapshot, nếu không một test chỉ “mong deny” có thể sai với hệ thống cố tình cho phép operation đã bắt đầu hoàn tất.

## 14. Những anti-pattern dễ mắc

| Anti-pattern | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| `Cache -> Auth` với cache chung dữ liệu nhạy cảm | Cache hit bypass kiểm tra quyền | Đưa enforcement ra ngoài cache, hoặc xác thực quyền trong mọi đường trả |
| Chỉ tin cached “allow” không có invalidation | Quyền bị thu hồi nhưng vẫn truy cập được | Policy version/expiry/invalidation/kiểm tra authoritative theo mức bảo đảm |
| Đưa user ID do client gửi vào cache key làm “bảo mật” | Giả mạo danh tính, rò chéo người dùng | Principal tin cậy, check policy thực |
| Chỉ chặn ở proxy, datastore cho gọi trực tiếp | Đường bypass vi phạm chính sách | Tăng bảo vệ ở boundary tin cậy, kiểm tra self-call |
| Mở transaction là tự hết TOCTOU | Quyền vẫn có thể đổi sau check | Isolation/lock/version và ràng buộc trên lệnh ghi |
| Cache.put trước transaction commit | Dữ liệu rollback vẫn được phục vụ | Ghi/invalidate sau commit và có recovery |
| Mọi denial đều rollback “toàn hệ thống” | Side effect bên ngoài không bị thu hồi | Thiết kế scope thực tế, audit và compensation |
| Denial bị outer fallback đổi thành giá trị cached | Truy cập trái phép trông như thành công | Giữ nguyên access-denied semantics |
| Không test cache đã ấm | Không phát hiện lỗi cấp quyền | Test warm-cache cross-principal/cross-tenant |
| Chỉ đo số request thành công | Mất dấu deny, attack/abuse | Metric phân loại deny và audit theo policy, không rò dữ liệu |

## 15. Checklist thiết kế trước khi đưa vào hoạt động

1. **Đơn vị được bảo vệ:** xác định action, resource, tenant, field và nguồn trusted principal.
2. **Điểm ra quyết định:** A lấy policy từ đâu, dùng snapshot/version nào và thu hồi quyền có độ trễ cho phép bao nhiêu.
3. **Mọi đường trả dữ liệu:** cache hit, miss, fallback, streaming, async và error paths đều phải chịu chính sách.
4. **Thứ tự thực tế:** ghi rõ các advice bao ngoài/bao trong và ai có thể không gọi `proceed()`.
5. **Transaction boundary:** check quyền có cần trong transaction không; dùng isolation/locking/optimistic version nào; audit có tách scope không.
6. **Cache semantics:** result cache hay decision cache, key gồm những thành phần nào, TTL và invalidation sau policy/data change ra sao.
7. **Commit và publish:** tránh cached uncommitted results; bảo đảm callback sau commit và kế hoạch xử lý lỗi.
8. **Chống bypass:** caller trực tiếp, self-call, background worker, database export, CDN và endpoint khác đều đã được phân tích.
9. **Không lộ thông tin:** timing, error, log, ETag, cache key, body/metadata đều theo cùng disclosure policy.
10. **Regression tests:** warm-cache cross-principal, cross-tenant, policy revocation, rollback/invalidation, TOCTOU và composition order.

Một cách nhớ thực tế: **kiểm soát truy cập phải bao phủ cả đường lấy dữ liệu từ cache; transaction phải bao phủ các thao tác cần bảo đảm trạng thái nhất quán; và cache phải chỉ phát dữ liệu hợp lệ với quyền cũng như trạng thái đã được phép công bố**. Thứ tự Advice là một phần của mô hình bảo mật và nhất quán, nên phải được đặc tả và kiểm chứng như chính hành vi nghiệp vụ.
