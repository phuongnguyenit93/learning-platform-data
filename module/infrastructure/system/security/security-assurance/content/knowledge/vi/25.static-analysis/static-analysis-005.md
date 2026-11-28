# Data flow analysis: Phân tích luồng dữ liệu trong Static Analysis cho Security Assurance

## 1. Data flow analysis là gì?

**Data flow analysis (DFA)** là phương pháp phân tích chương trình để suy ra **thông tin về giá trị, nguồn gốc, trạng thái và cách sử dụng dữ liệu khi dữ liệu di chuyển qua các lệnh và nhánh điều khiển** mà không nhất thiết phải thực thi chương trình với mọi input thực tế.

Trong **Static analysis**, DFA giúp trả lời các câu hỏi:

- Giá trị nào có thể đi tới một câu lệnh?
- Giá trị tại đây được định nghĩa ở đâu và đã bị thay đổi ra sao?
- Input không tin cậy có đi tới SQL, shell, file path hoặc HTTP client không?
- Dữ liệu nhạy cảm có đi tới log, response hay external service không?
- Một biến có thể null hoặc chưa được khởi tạo không?
- Một nhánh có thể đến được với điều kiện cụ thể không?
- Có đường đi nào đưa dữ liệu qua một sanitizer hoặc authorization check?
- Một method hoặc component có thể làm thay đổi trạng thái bảo mật nào?

Trong module **SECURITY_SECURITY_ASSURANCE**, kết quả DFA là **bằng chứng phân tích tĩnh có điều kiện**, phục vụ chuỗi:

**Security objective → Threat scenario → Requirement → Static-analysis rule/model → Finding/trace → Triage → Remediation → Security test → Verified evidence.**

DFA thường là nền tảng của **taint analysis**, kiểm tra lỗi injection, uncontrolled data flow và nhiều rule SAST. Nó cũng hỗ trợ compiler optimization và kiểm tra chất lượng mã, nhưng trong bài này trọng tâm là **bảo mật và assurance**.

> **Điểm cần nhớ:** DFA suy luận trên mô hình chương trình và các giả định của công cụ. Một cảnh báo là bằng chứng về một đường luồng đáng xem xét, không tự động chứng minh có exploit thực tế. Ngược lại, không có cảnh báo không chứng minh ứng dụng không có lỗ hổng.

### 1.1. Phân biệt data flow analysis với Data Flow Diagram

Hai khái niệm có tên gần nhau nhưng phục vụ mục đích khác:

| Khái niệm | Mức phân tích | Ví dụ | Đầu ra |
| --- | --- | --- | --- |
| **Data Flow Diagram (DFD)** | Kiến trúc/hệ thống | Browser → API → database | Luồng dữ liệu giữa thành phần, trust boundaries |
| **Static data flow analysis** | Code/program representation | Request parameter → variable → SQL call | Facts tại program points và path/source–sink |
| **Dynamic taint tracking** | Thực thi một số input thật | Dữ liệu có nhãn được truyền qua runtime | Những luồng quan sát được trong các executions |
| **Control flow analysis** | Khả năng chuyển điều khiển giữa basic blocks | if/else/loop/exception | Control Flow Graph, reachability |
| **Data lineage** | Hệ thống dữ liệu/analytics | Source table → ETL → report | Nguồn gốc dữ liệu qua data pipelines |
| **Information flow security** | Thuộc tính lan truyền thông tin | Secret không được ảnh hưởng public output | Chính sách noninterference/declassification tùy mô hình |

DFA dùng **Control Flow Graph (CFG)** để tính facts trên code. DFD ở tầng kiến trúc hỗ trợ xác định **sources/sinks và boundaries** cần mô hình hóa trong code. Cả hai có thể cùng phục vụ threat modeling nhưng không được đánh đồng.

### 1.2. Ví dụ nhỏ

~~~java
String search = request.getParameter("q");
String sql = "SELECT * FROM orders WHERE reference = '" + search + "'";
jdbcTemplate.execute(sql);
~~~

Câu hỏi của data flow analysis:

1. Giá trị **search** bắt nguồn từ dữ liệu do client kiểm soát?
2. Phép nối chuỗi có truyền tính **untrusted** tới **sql**?
3. **sql** có được truyền tới phương thức thực thi SQL?
4. Có cơ chế parameter binding, validation hoặc sanitizer nào giữa source và sink không?
5. Nếu không có, có cần báo **potential SQL injection** và test/review không?

Nhận diện này **không cần chạy một payload SQL cụ thể**, nhưng vẫn phải đánh giá API, connection context và khả năng khai thác thực tế trước khi kết luận.

## 2. Vì sao DFA cần thiết cho Security Assurance?

Một scanner chỉ tìm từ khóa có thể phát hiện **execute(sql)** nhưng không phân biệt:

- SQL được tạo từ constant tin cậy.
- SQL được nối với input của user.
- SQL dùng parameterized query đúng.
- SQL được hình thành sau nhiều method và wrapper.
- SQL thuộc đường code không reachable.
- SQL được lưu trong object rồi sử dụng ở một module khác.

DFA giúp đặt phát hiện vào **ngữ cảnh propagation của giá trị**, từ đó cải thiện chất lượng SAST và ưu tiên review.

### 2.1. Từ checklist đến evidence-based assessment

Một checklist “không được SQL injection” chưa đủ nếu không biết cách kiểm chứng. DFA có thể cung cấp:

- Source vị trí nhận dữ liệu không tin cậy.
- Các bước propagation và transformation.
- Sink nhạy cảm và API semantics.
- Những checks/sanitizers được công cụ nhận biết.
- File/line/function và call chain.
- Rule/query ID, tool version và scan configuration.
- Giả định về libraries, entry points và control flow.

Tuy nhiên phải kết hợp với:

- **Review code/architecture:** bảo đảm semantics của source, sink, validation.
- **Unit/integration tests:** xác nhận behavior trên build thật.
- **Runtime/cloud tests:** kiểm tra permissions và data access.
- **Threat model:** đánh giá reachability, attacker control và business impact.
- **Assurance review:** kiểm tra scope, evidence quality và residual risk.

### 2.2. Giá trị ở từng giai đoạn phát triển

| Giai đoạn | DFA hỗ trợ | Evidence cần giữ |
| --- | --- | --- |
| Design | Xác định untrusted/trusted data boundaries cần rule | Requirements, threat model, source–sink taxonomy |
| Development | Phản hồi sớm khi code tạo unsafe flow | IDE/PR finding, diff, reviewer |
| Build/CI | Quét code/version/rule set xác định | Scan ID, commit, config, SARIF/report |
| Triage | Xác định luồng và exploit conditions | Source–sink trace, applicability review |
| Fix | Thiết kế cắt unsafe path đúng vị trí | Patch, guard, API migration |
| Test | Kiểm tra hành vi theo threat | Positive/negative tests, build digest |
| Release | Không để bypass scanner hoặc unresolved blocker | Gate decision, exception |
| Operation | Theo dõi drift, vulnerability tái diễn | Scan trend, production artifact linkage |
| Audit | Chứng minh process và một phần code properties | Reviews, evidence lineage, closure |

## 3. Các khái niệm nền tảng: Program point, CFG và def-use

### 3.1. Program point

**Program point** là vị trí trước/sau một instruction hoặc statement mà ta muốn biết một fact.

Ví dụ:

~~~java
String input = request.getParameter("name");   // p1
String normalized = input.trim();              // p2
String msg = "Hello " + normalized;            // p3
logger.info(msg);                              // p4
~~~

Facts có thể là:

- Ở p1: input có nguồn gốc từ request parameter.
- Ở p2: normalized vẫn chịu ảnh hưởng input; trim không tự làm an toàn.
- Ở p3: msg được tạo từ input.
- Ở p4: message truyền vào logging sink chứa dữ liệu do client kiểm soát.

Nếu input là một secret từ nguồn bí mật, cùng luồng có thể liên quan **sensitive data disclosure** thay vì log injection.

### 3.2. Basic block và CFG

**Basic block** là đoạn lệnh có luồng điều khiển tuyến tính giữa điểm vào và điểm ra; **Control Flow Graph** nối basic blocks bằng các cạnh biểu diễn khả năng chuyển điều khiển.

~~~java
String value = request.getParameter("q");
if (value == null) {
    value = "";
}
String normalized = value.strip();
use(normalized);
~~~

CFG rút gọn:

~~~mermaid
flowchart TD
    A["Entry: value = request.getParameter(q)"] --> B{"value == null?"}
    B -- "true" --> C["value = empty string"]
    B -- "false" --> D["keep value"]
    C --> E["normalized = value.strip()"]
    D --> E
    E --> F["use(normalized)"]
~~~

Để suy ra giá trị tại **E**, engine phải **hợp nhất facts của các predecessor paths**. Nếu một nhánh an toàn và một nhánh còn tainted, kết quả hợp nhất phụ thuộc data-flow domain và operator.

### 3.3. Control flow khác data flow

**Control flow** hỏi: từ node A có thể thực thi node B không?

**Data flow** hỏi: nếu thực thi B, giá trị nào có thể tới B, từ đâu và thuộc trạng thái gì?

Hai mối quan hệ liên quan nhưng khác nhau. Một nhánh không reachable có thể loại bỏ data-flow path; ngược lại một edge trong CFG không chứng minh giá trị user input đi qua edge đó.

### 3.4. Definition và use

Một **definition (def)** ghi giá trị vào biến hoặc vị trí nhớ. Một **use** đọc giá trị đó.

~~~java
int total = 0;                 // def total #1
if (premium) {
    total = 100;               // def total #2
}
int fee = total / 10;          // use total, def fee
~~~

Tại use của total, có thể nhận definition #1 hoặc #2 tùy path. **Reaching definitions analysis** xác định definitions nào có thể đến use mà không bị ghi đè.

### 3.5. Def-use chain và use-def chain

- **Def-use:** từ một assignment, tìm các nơi sử dụng giá trị đó.
- **Use-def:** tại một use, tìm definitions có thể cấp giá trị đó.

Các liên kết này giúp trace:

**request input → intermediate variable → method argument → database query**.

Khi xử lý variables mutable, aliases, collections và heap, một định nghĩa không còn đơn giản là một dòng assignment; engine phải mô hình hóa memory location và side effects.

### 3.6. SSA và phi node

**Static Single Assignment (SSA)** cố gắng cho mỗi variable version chỉ được định nghĩa một lần. Giá trị hợp nhất giữa các nhánh được biểu diễn bằng **phi node**.

Ví dụ khái niệm:

~~~text
v1 = getUntrustedInput()
if condition:
    v2 = sanitize(v1)
else:
    v3 = v1
v4 = phi(v2, v3)
sendToSink(v4)
~~~

Nếu nhánh else vẫn đưa v1 chưa được bảo vệ vào sink, data-flow join phải giữ khả năng **untrusted**. Một call sanitize ở một path không đủ chứng minh tất cả paths an toàn.

SSA là một representation giúp analysis, không phải cách tự động bảo vệ dữ liệu.

## 4. Lý thuyết data-flow framework ở mức vừa đủ dùng

Một data-flow problem thường có:

1. **Program graph:** CFG hoặc interprocedural graph.
2. **Domain:** facts cần theo dõi.
3. **Transfer function:** mỗi instruction thay đổi facts thế nào.
4. **Merge/meet operator:** hợp nhất facts từ nhiều paths.
5. **Direction:** phân tích tiến (forward) hay lùi (backward).
6. **Boundary conditions:** facts ban đầu ở entry/exit.
7. **Solver:** thuật toán lặp tới fixpoint hoặc approximation.

### 4.1. Phương trình forward analysis

Với node n:

\[
IN[n] = \bigsqcup_{p \in pred(n)} OUT[p]
\]

\[
OUT[n] = F_n(IN[n])
\]

Trong đó:

- **IN[n]:** facts trước node.
- **OUT[n]:** facts sau node.
- **pred(n):** predecessors trong CFG.
- **F_n:** transfer function của node.
- **\(\bigsqcup\):** operator hợp nhất phù hợp domain; ví dụ **union** cho một may-taint analysis.

Không phải bài toán nào cũng dùng union: **must analysis** có thể dùng intersection/meet và điều kiện khởi tạo khác. Operator đúng phụ thuộc lattice và điều cần chứng minh.

### 4.2. Phương trình backward analysis

Với backward data-flow, lấy successors:

\[
OUT[n] = \bigsqcup_{s \in succ(n)} IN[s]
\]

\[
IN[n] = F_n(OUT[n])
\]

Ví dụ **liveness analysis** đặt câu hỏi biến nào có thể được dùng ở tương lai trước khi bị định nghĩa lại.

Trong security, backward slicing từ sink có thể tìm source hoặc paths có khả năng ảnh hưởng sink.

### 4.3. Domain, lattice và thứ tự thông tin

Một ví dụ domain đơn giản theo nguồn taint:

- **CLEAN:** không tìm được luồng untrusted trong mô hình.
- **TAINTED:** có thể chịu ảnh hưởng input không tin cậy.
- **UNKNOWN:** mô hình không xác định được trong tình huống cụ thể.

Những nhãn này chỉ minh họa. Một implementation có thể dùng **set of source IDs**, **set of taint kinds**, product lattice hoặc nhiều trạng thái context-specific. Nếu công cụ chọn UNKNOWN làm an toàn, có thể tạo false negative nghiêm trọng.

Với may-taint sử dụng tập nguồn:

- Domain: tập các source IDs có thể chảy tới program point.
- Bottom: tập rỗng.
- Merge: phép hợp tập.
- Assignment thường copy hoặc transform tập nguồn.
- Source instruction thêm source ID.
- Sanitizer có semantics tùy sink/context và có thể bỏ hoặc biến đổi một loại taint.
- Fixpoint: khi không còn facts thay đổi.

### 4.4. Transfer function và GEN/KILL

Đối với reaching definitions, có thể viết:

\[
OUT[n] = GEN[n] \cup (IN[n] \setminus KILL[n])
\]

- **GEN[n]:** definitions do node tạo.
- **KILL[n]:** definitions cũ bị ghi đè.
- **IN[n]:** definitions có thể đến node.
- **OUT[n]:** definitions có thể tiếp tục ra khỏi node.

Đối với taint, cùng ý tưởng **propagate/overwrite** phải xét phép gán mạnh/yếu và khả năng alias; không được áp dụng một GEN/KILL đơn giản cho mọi heap update.

### 4.5. Fixpoint và loops

Vòng lặp tạo CFG có chu trình:

~~~java
String result = "";
for (String piece : pieces) {
    result = result + piece;
}
send(result);
~~~

Engine lặp truyền facts qua các edges cho đến khi không còn thông tin mới. Với lattice hữu hạn chiều cao và transfer functions đơn điệu, solver kiểu worklist có thể hội tụ. Những domain vô hạn hoặc numerical abstraction phức tạp thường cần **widening/narrowing** để quản lý hội tụ.

### 4.6. Pseudocode worklist solver

~~~text
for every node n:
    IN[n]  = initial_fact(n)
    OUT[n] = initial_fact(n)

worklist = all_reachable_nodes

while worklist is not empty:
    n = remove_one(worklist)
    new_in  = merge(OUT[p] for p in predecessors(n))
    new_out = transfer(n, new_in)

    if new_in != IN[n] or new_out != OUT[n]:
        IN[n] = new_in
        OUT[n] = new_out
        add successors(n) to worklist
~~~

Đây là **pseudocode**, không phải solver tổng quát hoàn chỉnh; initialization, backward traversal, exceptions, call summaries và termination phụ thuộc bài toán.

## 5. Ví dụ làm tay: source → biến trung gian → sink

Xét chương trình:

~~~java
String user = request.getParameter("user");
String prefix = "welcome:";
String result;

if (enabled) {
    result = prefix + user;
} else {
    result = prefix;
}

logger.info(result);
~~~

Giả sử mục tiêu rule là xác định **untrusted data đi tới logging sink**.

### 5.1. Khởi tạo facts

- getParameter là source S-REQ.
- **user** mang taint set {S-REQ}.
- **prefix** có taint set rỗng.

### 5.2. Xử lý nhánh

- Nhánh enabled: result chứa {S-REQ}.
- Nhánh else: result chứa tập rỗng.
- Tại join: may-taint merge = {S-REQ} ∪ {} = {S-REQ}.

### 5.3. Sink

- logger.info(result) nhận một giá trị **có thể chịu ảnh hưởng bởi user**.
- Engine có thể báo taint path.
- Nhưng liệu đó là **vulnerability** phụ thuộc rule: log injection, log forging, high-cardinality logging, mức dữ liệu, encoding, log processor và policy.

**Một luồng untrusted tới logger không tự đồng nghĩa có lỗ hổng.** Reviewer cần xác định liệu giá trị nguy hiểm với sink cụ thể hay chỉ được ghi trong log đã được xử lý an toàn.

### 5.4. Taint không giống secret

Dữ liệu “không tin cậy” và “nhạy cảm” là hai loại nhãn khác:

- **Untrusted:** attacker có thể điều khiển nội dung; liên quan injection/SSRF/path traversal.
- **Sensitive:** thông tin cần được giới hạn nơi tiết lộ; liên quan confidentiality/privacy/secrets.
- Một giá trị có thể vừa untrusted vừa sensitive.
- Một giá trị được xác thực đầu vào vẫn có thể **không được phép tiết lộ**.
- Một secret được sinh nội bộ không phải untrusted input nhưng vẫn không được đưa vào public response.

Rule design cần **taint kinds** và sources/sinks phù hợp, không gom mọi dữ liệu vào một cờ Boolean.

## 6. Các bài toán data-flow kinh điển

| Bài toán | Direction thường gặp | Fact theo dõi | Ứng dụng bảo mật |
| --- | --- | --- | --- |
| **Reaching definitions** | Forward | Assignment nào có thể đến use | Truy vết nguồn dữ liệu |
| **Live variables** | Backward | Biến có thể dùng trước khi ghi đè | Code quality, hỗ trợ slicing |
| **Available expressions** | Forward must | Biểu thức chắc chắn đã tính | Compiler/analysis optimization |
| **Constant propagation** | Forward | Hằng số hoặc unknown | Xác định branch/path và insecure flags |
| **Nullness analysis** | Forward | Null/non-null/maybe null | NPE, error-path analysis |
| **Taint analysis** | Forward hoặc backward | Untrusted/sensitive source provenance | Injection, disclosure, unsafe dataflow |
| **Typestate/resource analysis** | Nhiều hướng/model | State transition của object/resource | Unclosed resource, invalid API sequence |
| **Range/interval analysis** | Forward | Khoảng giá trị số | Bounds, overflow, validation |
| **Value-set analysis** | Forward | Khả năng giá trị biến/địa chỉ | Pointer targets, unsafe calls |
| **Security slicing** | Forward/backward | Statements ảnh hưởng một source/sink | Triage và review hẹp hơn |

Không phải công cụ SAST nào cũng hỗ trợ tất cả bài toán hay cùng độ chính xác. Một engine chủ yếu pattern matching có thể báo đúng một số trường hợp nhưng **không nên gọi nó là path-sensitive interprocedural DFA** nếu thực tế không có.

### 6.1. Taint analysis phổ biến vì sao?

Security flaws thường xuất hiện khi **dữ liệu từ trust level thấp ảnh hưởng operation có quyền cao hơn**:

- String điều khiển SQL được thực thi với database privilege.
- Request URL làm server gửi HTTP request.
- File path xác định resource đọc/ghi.
- HTML content chuyển thành executable script trong browser.
- Untrusted value đi tới shell interpreter.
- Secret/PII đi tới logging hoặc external disclosure.
- Tenant/role từ request được dùng như trusted authorization fact.

Taint analysis giúp nhận biết ứng viên của những luồng này, nhưng **business authorization invariants** và stateful workflows thường cần mô hình semantic hoặc tests bổ sung.

## 7. Taint analysis: source, sink và sanitizer

### 7.1. Source

**Source** là API hoặc điểm tạo dữ liệu cần theo dõi.

Ví dụ sources cho untrusted input:

- HTTP path/query/body/header/cookie.
- WebSocket message.
- Queue/event payload từ producer có trust không được đảm bảo.
- File upload content, filename hoặc metadata.
- External API responses và webhook.
- Environment variables nếu kẻ tấn công có thể ảnh hưởng context.
- Database field từng được lưu từ user input.
- Command-line arguments hoặc plugin/extension input.

Ví dụ sources cho sensitive data:

- Secret manager response.
- Access/refresh token, credential, API key.
- PII/health/financial records theo data classification.
- Private key và signing material.
- Service-generated confidential documents.

Một trường database **không mặc định trusted** chỉ vì đã qua persistence; cần xét ai có thể ghi vào đó và data lineage.

### 7.2. Sink

**Sink** là operation cần ràng buộc dữ liệu khi dùng:

| Sink class | Ví dụ | Security concern |
| --- | --- | --- |
| SQL execution | Xây raw SQL statement | Injection |
| OS command execution | Runtime.exec/shell | Command injection |
| HTTP client | URL/host/path từ request | SSRF, data exfiltration |
| File path | Files.read/write/delete | Path traversal |
| Template/HTML | Unsafe HTML/DOM sink | XSS |
| XML/XPath | Dynamic expression/parser | Injection, XXE nếu parser sai cấu hình |
| Logging | Raw secret/PII hoặc unescaped log entries | Confidentiality/log forging |
| Public response | Trả object chứa sensitive fields | Data disclosure |
| Message broker | Publish vào topic không phù hợp | Wrong-tenant/data leak |
| Deserialization | Untrusted serialized object | Unsafe object construction |
| Authorization decision | Role/tenant do client tự khai | Privilege escalation |
| Database mutation | Amount/state/owner từ untrusted body | Business logic tampering |

Một API có thể là sink cho **taint kind A** nhưng an toàn cho **taint kind B**. Ví dụ HTML encoding đúng context không thay thế SQL parameterization.

### 7.3. Sanitizer và validation

Một **sanitizer** là phép biến đổi hoặc kiểm tra được mô hình hóa là làm giảm một loại rủi ro ở một sink **với điều kiện cụ thể**.

Cần phân biệt:

- **Normalization:** chuẩn hóa chữ/Unicode/path, không tự làm an toàn.
- **Validation:** reject input không hợp lệ dựa trên schema/allowlist.
- **Encoding:** encode cho một output context, ví dụ HTML text/attribute/JS string khác nhau.
- **Parameterization:** tách dữ liệu khỏi cú pháp SQL; thường nên dùng thay escape thủ công.
- **Canonicalization + containment:** dùng cho file paths, kèm kiểm tra thư mục đích và symlink/race.
- **Authorization:** xác minh actor có quyền trên resource/action/context; không thể thay bằng string sanitizer.
- **Declassification:** quyết định chính sách cho phép tiết lộ một phần dữ liệu nhạy cảm, có điều kiện.

Hàm tên **sanitize()** không tự làm một giá trị an toàn. Công cụ phải biết semantics thật, context và điều kiện thực thi.

### 7.4. Validation một nhánh không đủ

~~~java
String value = request.getParameter("target");

if (isAllowedTarget(value)) {
    audit.info("allowed");
}

httpClient.get(value);
~~~

Nếu validator chỉ ghi log hoặc không chặn nhánh invalid, source vẫn đi tới sink. Static analyzer phải xem **control dependence** hoặc predicate semantics, không được xem sự xuất hiện của isAllowedTarget là đủ.

### 7.5. Tránh sanitizer không đúng context

Ví dụ:

- HTML-encode trước khi xây SQL không ngăn SQL injection.
- SQL-escape trước khi tạo HTML không ngăn XSS.
- Strip dấu chấm khỏi path không đủ chống traversal/encoding variants.
- Chặn chuỗi localhost trong URL không bao phủ DNS rebinding hoặc redirects.
- Truncate token trong log có thể vẫn tiết lộ phần bí mật đủ nhạy cảm theo policy.
- JWT signature verified không cho phép bỏ resource authorization.

## 8. Các chiều độ chính xác của data-flow analysis

### 8.1. Flow-sensitive vs flow-insensitive

**Flow-sensitive** xem thứ tự instructions, có thể phân biệt biến bị ghi đè trước sink:

~~~java
String x = request.getParameter("q");
x = "constant";
use(x);
~~~

Một analysis flow-sensitive có thể biết x ở use không còn phụ thuộc q. Flow-insensitive chỉ tổng hợp assignments cho variable có thể báo quá rộng.

Tuy nhiên nếu có aliases/side effects, việc loại bỏ taint chỉ vì thấy assignment có thể không đúng cho memory locations liên quan.

### 8.2. Path-sensitive vs path-insensitive

**Path-sensitive** theo dõi điều kiện branch để nhận diện các đường khả thi:

~~~java
String input = request.getParameter("q");
if (input == null) {
    return;
}
if (isTrustedConstant(input)) {
    doSafeAction();
} else {
    doOtherAction();
}
~~~

Một engine path-insensitive có thể kết hợp facts từ những branches loại trừ nhau, sinh false positive. Path-sensitive tăng độ chính xác nhưng có nguy cơ **path explosion**, đặc biệt với nhiều nhánh và loops.

### 8.3. Context-sensitive vs context-insensitive

Cùng một method được gọi từ hai contexts:

~~~java
String safe = transform("constant");
String unsafe = transform(request.getParameter("q"));
~~~

Context-sensitive analysis có thể phân biệt kết quả theo call site, parameter mapping hoặc call string/object context. Context-insensitive analysis có thể hợp nhất nguồn và tạo cảnh báo ở safe call.

### 8.4. Field-sensitive vs field-insensitive

~~~java
class Event {
    String publicLabel;
    String secretToken;
}
~~~

Field-sensitive analysis theo dõi **publicLabel** và **secretToken** riêng. Field-insensitive có thể gộp toàn object là tainted/sensitive, dẫn đến báo rộng hoặc bỏ sót tùy abstraction.

### 8.5. Object- và heap-sensitive

Khi có:

- Collections, maps và arrays.
- Mutable objects.
- Shared references.
- DI container và singleton state.
- ORM entities và proxies.
- Reflection và generated code.

Engine cần mô hình alias/pointer targets và heap locations. Một method **event.setTenantId()** có thể thay state của nhiều alias cùng tham chiếu.

### 8.6. Strong update vs weak update

**Strong update** có thể xóa fact cũ nếu chắc chắn ghi đè **đúng một** memory location.

**Weak update** giữ cả giá trị cũ và mới nếu assignment có thể ảnh hưởng nhiều locations do aliasing.

Một implementation dùng strong update sai khi có aliases có thể tạo **false negative**, nguy hiểm hơn một trace dư.

### 8.7. Interprocedural vs intraprocedural

**Intraprocedural:** phân tích trong một function/method.

**Interprocedural:** theo values qua call/return, parameters, captured state, exceptions và side effects giữa methods.

Các lỗ hổng thực tế thường đi qua:

**Controller → Service → Repository → HTTP client / Database**.

Nếu engine dừng ở method boundary hoặc framework API không được mô hình hóa, sẽ mất trace.

### 8.8. Precision vs performance trade-off

| Lựa chọn | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| Flow-sensitive | Biết overwrite/thứ tự | Thêm trạng thái mỗi program point |
| Path-sensitive | Giảm impossible-path false positives | Explosion trên nhánh, loops |
| Context-sensitive | Phân biệt call sites | Tăng call graph states |
| Field-sensitive | Ít gộp data trong object | Phức tạp heap/model |
| Interprocedural | Tìm long data paths | Cần call graph/summaries |
| Incremental analysis | PR feedback nhanh | Cần đảm bảo baseline/changed code coverage |
| Bounded analysis | Kiểm soát thời gian | Có thể bỏ long paths |
| Whole-program analysis | Bao quát hơn | Tốn thời gian, phụ thuộc build completeness |

**Không có cấu hình “chính xác nhất” miễn phí**. Assurance cần biết analysis budget, giới hạn engine và target finding classes.

## 9. Interprocedural data flow và framework modeling

### 9.1. Call graph

Call graph biểu diễn các quan hệ khả dĩ giữa caller và callee. Trong Java, việc xác định call target khó hơn khi có:

- Interface và dynamic dispatch.
- Inheritance và overridden methods.
- Reflection.
- Spring dependency injection/proxies.
- Lambdas và method references.
- Annotation-driven controllers/listeners.
- Serialization/deserialization.
- Framework callbacks.
- Generated code hoặc bytecode instrumentation.
- Native/JNI operations.
- Service-to-service calls vượt process boundary.

Thiếu target calls có thể tạo false negative; thêm quá nhiều target giả có thể tạo false positive.

### 9.2. Method summaries

Một method summary mô tả cách method biến đổi facts mà không cần phân tích lại toàn thân ở mọi call.

Ví dụ summary khái niệm:

~~~text
normalize(input):
    return_taint = input_taint

maskSecret(secret):
    return_sensitivity = depends_on_masking_contract

databaseQuery(sqlText):
    sink = SQL_TEXT_EXECUTION

jdbcQuery(sqlTemplate, parameters):
    sqlTemplate must be trusted SQL structure
    parameters are treated as data values, not SQL syntax
~~~

Đây là **model giả định**, không phải đặc tả chính xác của một thư viện/engine SAST. Summary phải đúng API overload và semantic conditions.

### 9.3. Java framework sources/sinks

Ở Spring Boot, ví dụ sources có thể là:

- @RequestParam.
- @PathVariable.
- @RequestBody.
- HttpServletRequest.getParameter/getHeader.
- Webhook payload DTO.
- Kafka/JMS message payload.
- Redis/database contents do user ghi trước đó.

Sinks có thể nằm ở:

- JDBC Statement/raw SQL string execution.
- ProcessBuilder/shell.
- HTTP client URL builder.
- Files/path APIs.
- HTML/template unsafe output.
- Logging/telemetry.
- Secret/external data export.
- Resource lookup/authorization.

Với Spring Data JPA, phương thức repository có thể ẩn SQL thật; engine không phải lúc nào cũng hiểu mọi derived query hoặc custom native query. Cần **framework models, code review và integration tests**.

### 9.4. Distributed data flows

Một static analyzer chỉ xem một repo có thể không theo được:

**API producer → serialized Kafka event → worker consumer → object storage**.

Để đánh giá end-to-end:

- Nối kết quả analyzer nhiều modules nếu được hỗ trợ.
- Dùng contract/schema và trust boundary review.
- Đánh dấu message fields có source provenance.
- Kiểm thử worker với forged/replayed/modified events.
- Xem quyền workload tại sinks.
- Dùng DFD và runtime audit để bổ sung evidence.

Không tuyên bố một công cụ single-repo đã chứng minh an toàn của toàn bộ distributed architecture.

## 10. Sources và sinks theo threat model

Không phải mọi nơi nhập dữ liệu đều cùng trust level. Tạo taxonomy theo application:

| Threat class | Source | Sink | Security invariant |
| --- | --- | --- | --- |
| SQL injection | Request q/filter | SQL text executor | Data không thay SQL structure |
| Command injection | Job parameters | Shell command | Untrusted data không trở thành command |
| SSRF | User callback URL | Server HTTP client | Chỉ kết nối approved destinations |
| Path traversal | Filename/path từ client | File read/write | Giới hạn trong allowed resource scope |
| XSS | Stored/reflected user text | Browser HTML/DOM | Contextual encoding/safe DOM APIs |
| Log disclosure | Credentials/PII | Log/trace/error | Không lưu raw secret/sensitive fields |
| Unauthorized export | User-selected tenant/data | Report/file/message sink | Resource authorization trước release |
| Deserialization abuse | Untrusted serialized bytes | Unsafe object construction | Enforce safe types/formats/limits |
| Tenant spoofing | X-Tenant-Id client header | DB query/resource decision | Trusted tenant context only |
| Secret exfiltration | Secret store response | External HTTP/client response | Secrets only to approved consumers |
| Weak crypto use | Sensitive plaintext | Cryptographic API | Approved protection/configuration |
| Business logic tampering | Amount/owner fields | DB mutation/refund | Server-side invariant and authorization |

DFA hỗ trợ phát hiện **dòng giá trị**, nhưng có những security requirements đòi đánh giá **state transitions, business invariants, control dependencies hoặc external authorization**. Cần không đồng nhất tất cả với một source–sink rule.

## 11. Ví dụ Java/Spring Boot: SQL injection qua dữ liệu người dùng

### 11.1. Code rủi ro

Giả sử có API search order theo reference:

~~~java
@GetMapping("/orders/search")
public List<OrderView> search(@RequestParam String ref) {
    String sql = "SELECT id, reference FROM orders WHERE reference = '"
            + ref + "'";
    return jdbcTemplate.query(sql, orderMapper);
}
~~~

Một trace có thể là:

~~~mermaid
flowchart LR
    A["@RequestParam ref (untrusted source)"] --> B["String concatenation"]
    B --> C["SQL query text"]
    C --> D["JdbcTemplate.query(sql) sink"]
    D --> E[("Database with service privileges")]
    F["No parameter binding in this path"] -. "finding evidence" .-> D
~~~

**DFA facts:**

1. Ref nhận giá trị từ HTTP.
2. Concatenation đưa ref vào SQL syntax text.
3. SQL text truyền vào query call.
4. Analyzer gắn source–sink path.
5. Reviewer đánh giá exploit conditions, affected permissions và query execution semantics.

Không cần cung cấp payload phá hoại để minh họa một injection risk.

### 11.2. Thiết kế sửa bằng parameter binding

~~~java
@GetMapping("/orders/search")
public List<OrderView> search(@RequestParam String ref) {
    String sql = """
            SELECT id, reference
            FROM orders
            WHERE reference = ?
            """;

    return jdbcTemplate.query(sql, orderMapper, ref);
}
~~~

**Parameter binding** tách dữ liệu input khỏi cấu trúc câu SQL, giảm nguy cơ SQL injection từ tham số ref khi API được dùng đúng. Nhưng cần kiểm tra:

- Dynamic table/column/order-by expressions nếu có: parameters không thay identifier SQL.
- Tenant scope và object authorization.
- Field-level masking và data classification.
- Input length/rate limits để tránh resource exhaustion.
- Driver và library behavior tương ứng.
- SQL privilege của service account.
- Các query khác có cùng anti-pattern.

**Truy vấn parameterized có thể hết SQL injection nhưng vẫn rò dữ liệu nếu thiếu authorization**.

### 11.3. Unit test không đủ cho DB integrity

Một mock JdbcTemplate test có thể chứng minh controller gọi SQL dạng có placeholder, nhưng không tự xác minh:

- Driver thực xử lý parameter binding đúng.
- Query thật có tenant constraint.
- DB role/RLS áp dụng đúng.
- Endpoint other path không dùng unsafe SQL.
- Staging/prod đang chạy build đã sửa.

Nên bổ sung integration tests với DB/SQL layer đại diện và security tests trên API.

## 12. Ví dụ Java: Log leakage và taint kinds

Một giá trị có thể là **sensitive source** dù người dùng không kiểm soát.

### 12.1. Mã rủi ro

~~~java
String accessToken = tokenProvider.getAccessToken();
logger.info("Using access token: {}", accessToken);
~~~

DFA có thể model:

**tokenProvider.getAccessToken → sensitive-taint → logger.info sink**.

Nhưng nếu engine chỉ có untrusted-input taint rules, nó có thể **không báo lộ secret**. Rule cần taint kind hoặc data classification phù hợp.

### 12.2. Sửa theo mục tiêu bảo mật

~~~java
String accessToken = tokenProvider.getAccessToken();
logger.info("Request to partner initiated, correlationId={}",
        correlationId);
partnerClient.callWithToken(accessToken);
~~~

Vẫn cần review:

- HTTP client có vô tình log Authorization header qua debug interceptor?
- Exceptions/traces có dump request headers?
- Third-party telemetry có lưu tokens?
- Correlation ID có chứa PII hoặc attacker-controlled control characters?
- Token được dùng ở authorized destination?
- Token lifecycle/rotation và response masking?

Không nên “sanitize” access token bằng cách cắt vài ký tự rồi log nếu policy cấm lưu raw/semi-raw secret.

## 13. Ví dụ Java: SSRF và network sinks

### 13.1. Unsafe dynamic URL

~~~java
@GetMapping("/preview")
public String preview(@RequestParam String url) {
    return restClient.get().uri(url)
            .retrieve().body(String.class);
}
~~~

Một static taint rule có thể thấy:

**HTTP request parameter → RestClient URI → outbound request**.

Đây là **SSRF candidate** nếu attacker có thể điều khiển destination theo cách cho phép chạm internal metadata/admin services.

### 13.2. Không có một sanitizer chuỗi đơn giản nào đủ

An toàn cần xem:

- URL parser/canonicalization chính xác.
- Scheme allowlist, thường chỉ cần những protocols cụ thể.
- Hostname/domain allowlist gắn purpose.
- Redirect policy: không tự theo tới đích ngoài allowlist.
- DNS resolution, rebind và IPv4/IPv6.
- Private/link-local/loopback/metadata addresses.
- Egress firewall/proxy policy.
- TLS verification và outbound credentials.
- Request timeout, size, method và retry limits.
- Client có DNS caching hoặc proxy behavior gì.
- Có thể chuyển sang **server-side fixed destinations** thay vì user-supplied URL không?

DFA chỉ hỗ trợ tìm giá trị đi tới HTTP client; **network-level controls và runtime tests** mới giúp xác minh chặn đích không mong muốn.

### 13.3. Thiết kế giảm attack surface

Nếu nghiệp vụ chỉ cần lấy metadata của ba partner, có thể đưa destination vào **trusted server-side mapping**, cho user chọn partner ID, không nhập arbitrary URL.

~~~java
public URI endpointFor(Partner partner) {
    return switch (partner) {
        case ALPHA -> URI.create("https://alpha.partner.example/api");
        case BETA -> URI.create("https://beta.partner.example/api");
        case GAMMA -> URI.create("https://gamma.partner.example/api");
    };
}
~~~

Hostnames là **giả định minh họa**. Vẫn cần outbound identity, TLS, timeout, redirects/egress và credential scope theo architecture.

## 14. Ví dụ Java: File path và traversal

### 14.1. Rủi ro

~~~java
public byte[] download(String requestedPath) throws IOException {
    return Files.readAllBytes(
            Paths.get("/srv/exports/" + requestedPath));
}
~~~

Nếu requestedPath đến từ HTTP, một analyzer có thể phát hiện:

**path parameter → string join → file read sink**.

Một validation như “không chứa dấu chấm chấm” không đủ với encoding, separators, symlink, canonicalization và race.

### 14.2. Thiết kế hạn chế input

Một giải pháp giảm attack surface là **chỉ chấp nhận export ID được server quản lý**, tra cứu metadata/owner trong DB rồi sử dụng storage key nội bộ thay vì cho client cung cấp arbitrary path.

~~~java
public byte[] downloadExport(
        UUID exportId,
        VerifiedPrincipal caller) throws IOException {
    ExportRecord record = exportRepository
            .findAuthorized(exportId, caller.subjectId(), caller.tenantId())
            .orElseThrow(ResourceNotFoundException::new);

    Path base = exportRoot.toRealPath();
    Path candidate = base.resolve(record.serverManagedFilename()).normalize();

    if (!candidate.startsWith(base)) {
        throw new SecurityException("Export path outside allowed root");
    }

    return Files.readAllBytes(candidate);
}
~~~

**Giới hạn cần review:** đoạn này minh họa authorization và lexical/real base containment, **chưa giải quyết đầy đủ symlink race/TOCTOU** nếu attacker có thể sửa cây filesystem. Trong môi trường có untrusted filesystem actors, cần lựa chọn storage API/capability và open semantics an toàn (ví dụ no-follow, directory handles) theo OS/runtime; có thể tốt hơn sử dụng object storage keys và bucket policy. Cần test cả authorized/unauthorized export, symlink handling và worker-generated filenames.

## 15. Ví dụ: Data flow không tự chứng minh tenant authorization

### 15.1. Mã trông “có tenant” nhưng nguy hiểm

~~~java
@GetMapping("/orders/{id}")
public OrderView getOrder(
        @PathVariable UUID id,
        @RequestHeader("X-Tenant-Id") UUID tenantId) {

    return repository.findByIdAndTenantId(id, tenantId)
            .map(OrderView::from)
            .orElseThrow(ResourceNotFoundException::new);
}
~~~

Query có tenant filter nhưng tenantId đến từ **header do client tự khai**. User A có thể truyền tenant B.

Đường DFA đáng theo dõi:

**Untrusted header → tenantId → repository authorization-relevant query parameter**.

Tuy nhiên, một taint analyzer chỉ biết SQL injection có thể không báo, vì **parameterized SQL không bị injection**. Vấn đề là **trust/authorization semantics** của tenant ID.

### 15.2. Sửa bằng trusted principal

~~~java
@GetMapping("/orders/{id}")
public OrderView getOrder(
        @PathVariable UUID id,
        Authentication authentication) {

    VerifiedPrincipal principal = principalResolver
            .fromVerifiedAuthentication(authentication);

    permissionService.requireAllowed(
            principal, "orders.read", principal.tenantId());

    return repository
            .findByIdAndTenantId(id, principal.tenantId())
            .map(OrderView::from)
            .orElseThrow(ResourceNotFoundException::new);
}
~~~

Một thiết kế hoàn chỉnh còn phải:

- Xác thực issuer/audience/signature/expiry và principal mapping.
- Kiểm tra tenant membership còn hiệu lực.
- Kiểm tra subject–action–resource nếu role không đủ.
- Đảm bảo repository thật có tenant query đúng.
- Không lộ qua cache/search/export/worker.
- Xác minh support/admin cross-tenant use cases có case/approval scope.
- Không fail-open khi policy service unavailable.
- Audit decisions theo policy.
- Kiểm tra quyền lúc actual resource access, tránh stale authorization.

**DFA hỗ trợ review source của tenant value, không thay integration tests về authorization.**

## 16. Sơ đồ trace của một finding theo nhiều method

Ví dụ controller gọi service, service gọi repository, repository tạo raw SQL:

~~~mermaid
flowchart TD
    A["HTTP /api/orders/search?q=user-input"] --> B["OrderController.search(q)"]
    B --> C["OrderService.search(q)"]
    C --> D["OrderQueryBuilder.build(q)"]
    D --> E["Raw SQL text"]
    E --> F["JdbcTemplate.execute(sql)"]
    F --> G[("Orders Database")]
    H["Source model: request parameter"] -.-> A
    I["Propagation models: assignments, call arguments, returns"] -.-> C
    J["Sink model: SQL-text execution"] -.-> F
    K["Security finding: potential SQL injection"] -.-> E
~~~

Trong report, reviewer cần phân biệt:

- **Observed code path:** analyzer tìm được các call/value steps.
- **Assumed path:** engine dựng thêm do dynamic dispatch/unknown calls.
- **Validated sanitizer:** engine chứng minh một transform đúng trong điều kiện cụ thể.
- **Unknown:** dynamic reflection/native/serialization mà engine không mô hình đầy đủ.
- **Exploitability:** cần thêm threat context và testing.

### 16.1. Trace có phải bằng chứng exploit?

Không. Static trace thường chứng minh **một luồng có thể tồn tại theo model**, không phải attacker đã khai thác, SQL executor thực sự chạy với payload nào hoặc database đã bị lộ.

Ngược lại, nếu test thực tế tái hiện lỗi, evidence runtime bổ sung nâng độ chắc chắn. Không nên đòi một exploit destructive để tin mọi static finding.

### 16.2. Trace path dài có thể đánh lạc hướng

Một report 25 bước call chain có thể gồm nhiều wrapper hợp lệ, nhưng security question vẫn là:

- Source có thật sự untrusted trong deployment?
- Có chỗ biến thành trusted context đúng policy?
- Sink có nghĩa gì ở overload/API cụ thể?
- Có chặn bởi branch cần thiết?
- Có permission constraints giảm impact?
- Có alternative path không?

Độ dài trace không phải severity.

## 17. False positives và false negatives trong DFA

### 17.1. False positive

**False positive** là cảnh báo không tương ứng với vulnerability thật trong phạm vi đã xác minh.

Nguyên nhân:

- Source thực tế chỉ nhận input từ trusted service nhưng model chung.
- Analyzer hợp nhất hai branches không thể cùng xảy ra.
- Không hiểu sanitizer/parameter-binding API.
- Không biết method đã được wrap bởi guard đúng.
- Không phân biệt object fields hoặc contexts.
- Code không nằm trong deploy artifact.
- Scanner hiểu sai framework behavior.

Không nên suppress chỉ dựa vào cảm giác. Cần ghi **evidence và conditions** cho triage.

### 17.2. False negative

**False negative** là lỗ hổng tồn tại nhưng tool không báo.

Nguyên nhân:

- Không nhận biết source/sink/framework.
- Không phân tích interprocedural hoặc async path.
- Reflection/native/dynamic dispatch không được xử lý.
- Taint propagation mất qua serializer/ORM/DTO.
- Model sanitizer quá rộng, cho rằng mọi output an toàn.
- Paths bị cắt do analysis timeout/budget.
- Chỉ scan changed files, bỏ inherited dangerous code.
- File/code generated hoặc module không được build/index.
- Language/framework/tool version không được hỗ trợ.
- Business logic flaw không biểu diễn được bằng taint model.

**Không có finding không tương đương không có vulnerability**, nhất là trong business logic, permission invariants và distributed workflows.

### 17.3. Soundness và completeness

Trong static analysis:

- Một **sound may-analysis** theo mô hình cố gắng không bỏ sót behaviors thuộc phạm vi trừu tượng, đổi lại có thể báo những paths không thể thực thi thực.
- Một analysis thiên về precision hoặc performance có thể sử dụng heuristics, bounded paths hoặc modeling gaps.
- Completeness/precision và soundness được định nghĩa theo analysis property, language semantics và assumptions, không nên tuyên bố chung “tool sound”.

**Không dùng chữ sound một cách tuyệt đối** khi engine không bao phủ reflection, native operations hoặc dynamic language features.

### 17.4. Triaging có trách nhiệm

Một workflow phù hợp:

1. Xác nhận finding ID, code revision và rule.
2. Đọc source–sink trace.
3. Xác nhận attacker control và data classification.
4. Xác định reachability, required privileges và environment.
5. Review guard/sanitizer semantics và bypass paths.
6. Kiểm tra actual artifact và affected services.
7. Đánh giá impact và compensating controls.
8. Chọn treatment: fix, investigate, not applicable, false positive hoặc authorized exception.
9. Giữ rationale/evidence và reviewer.
10. Reopen khi source/model/config/architecture thay đổi.

Việc gắn **FALSE_POSITIVE** phải có căn cứ; **LOW_PRIORITY** không tương đương FALSE_POSITIVE.
## 18. Những luồng khó: implicit flow, aliasing và external state

### 18.1. Explicit information flow

**Explicit flow** xảy ra khi dữ liệu được copy, tính toán hoặc đưa trực tiếp vào giá trị mới.

~~~java
String secret = secretStore.read("api-key");
String copied = secret;
return copied;
~~~

Một sensitive-taint engine tương đối đơn giản có thể theo trace:

**secretStore.read → secret → copied → HTTP response**.

### 18.2. Implicit information flow

**Implicit flow** xảy ra khi một secret ảnh hưởng điều khiển, từ đó ảnh hưởng public output, dù secret không được copy trực tiếp.

~~~java
boolean privileged = account.isPrivileged();
String result;

if (privileged) {
    result = "yes";
} else {
    result = "no";
}

return result;
~~~

Nếu **privileged** là thông tin nhạy cảm, public output tiết lộ một bit thông tin qua control dependence. Một taint analyzer chỉ theo **explicit assignments** có thể không nhận ra.

Có những hệ thống cần ngăn thông tin rò qua implicit flows, nhưng theo dõi mọi control dependence có thể tạo lượng lớn cảnh báo không thực tế. Cần threat model và **information-flow policy** cụ thể.

### 18.3. Timing và side channels

Ngay cả khi public result giống nhau, execution time, resource use, error code hoặc response size có thể tiết lộ bí mật. DFA thông thường **không chứng minh constant-time behavior** hoặc không có side channel. Với crypto/protocol cực nhạy, cần review và testing chuyên biệt.

### 18.4. Alias và mutation

~~~java
List<String> values = new ArrayList<>();
List<String> alias = values;

values.add(request.getParameter("q"));
send(alias.get(0));
~~~

Một engine không hiểu alias **values/alias** có thể mất propagation. Tương tự, đối tượng truyền qua setter/getter, collection wrappers và ORM hydration cần heap/field models chính xác.

### 18.5. Serialization boundary

~~~text
Producer receives untrusted tenant field
    -> JSON serialization
    -> Kafka message
    -> Consumer DTO
    -> Repository query
~~~

Nếu scanner không phân tích cả producer và consumer, cần dùng DFD/contract + tests để xác định **trust provenance** ở boundary; việc field được deserialize thành UUID không làm tenant đáng tin.

### 18.6. Declassification và policy

Một số thông tin nhạy cảm được phép công bố sau khi biến đổi được kiểm soát, ví dụ aggregate statistics đã qua đánh giá disclosure risk.

Một rule “mọi sensitive source không bao giờ đi tới public sink” có thể quá chặt hoặc không đủ chính xác. Cần:

- Data classification và purpose.
- Authorized disclosure paths.
- Aggregation/redaction semantics.
- Small-group leakage risks.
- Reviewer, policy và evidence.
- Negative tests cho sai purpose, scope, recipient.

**Declassification là quyết định bảo mật có điều kiện**, không chỉ đặt tên một function cho analyzer bỏ taint.

## 19. Xây mô hình data-flow phù hợp một ứng dụng

### 19.1. Các bước thiết kế rule

1. Xác định **security objective** và threat class.
2. Chọn **source kinds**: untrusted, secret, PII, tenant context, privilege claims.
3. Chọn **sink kinds**: SQL, HTTP, shell, file, response, log, privileged data access.
4. Ghi **propagation semantics** cho assignments, method returns, wrappers, collections.
5. Ghi **sanitizers/validators** đúng context và điều kiện.
6. Xem những framework entry points và callbacks.
7. Định nghĩa **scope**: languages, modules, runtime, dependencies.
8. Tạo positive/negative fixtures.
9. Test rule với safe và unsafe code patterns.
10. Chọn severity/priority mapping và triage workflow.
11. Version hóa rule/model/config, có reviewer.
12. Theo dõi false positives/false negatives và cải thiện.

### 19.2. Source/sink catalog mẫu

| Model ID | Kind | API/Boundary | Notes |
| --- | --- | --- | --- |
| SRC-HTTP-01 | UNTRUSTED | Spring request parameters | Caller có thể kiểm soát |
| SRC-HTTP-02 | UNTRUSTED | HTTP headers/body | Một số headers có thể được proxy bảo vệ; cần trust model |
| SRC-QUEUE-01 | UNTRUSTED | Event payload from external producer | Verify provenance và schema |
| SRC-SECRET-01 | SENSITIVE | Secret store/key retrieval | Không chảy tới public sinks |
| SRC-PII-01 | SENSITIVE | Customer record fields | Output/analytics theo policy |
| SRC-TENANT-01 | UNTRUSTED_AUTH_CONTEXT | Client tenant header | Không dùng làm verified ownership |
| SINK-SQL-01 | SQL_TEXT | Raw statement execution | Tìm concatenated/untrusted SQL structure |
| SINK-HTTP-01 | NETWORK_DESTINATION | Outbound client URI | SSRF và exfiltration |
| SINK-LOG-01 | LOG_DISCLOSURE | Logger/tracer | Secrets/PII redaction |
| SINK-RESP-01 | PUBLIC_OUTPUT | API response | Sensitive information policy |
| SINK-FILE-01 | FILE_PATH | Read/write/delete APIs | Path traversal/authorization |
| SINK-PRIV-01 | AUTHORIZATION_INPUT | Tenant/role decision | Caller-controlled trust injection |

Ví dụ trên là **catalog đề xuất**. Cấu hình thực của CodeQL, Semgrep hay một engine khác sẽ có cú pháp và khả năng riêng; không chuyển bảng này thành executable rule một cách máy móc.

### 19.3. Sanitizer model phải có điều kiện

Một model dễ gây false negative:

~~~text
function named "sanitize*" -> remove all taint kinds
~~~

Đây là **anti-pattern**: một hàm có thể chỉ trim whitespace. Thay vào đó:

~~~text
parameterized SQL binding:
    untrusted data is allowed as data parameter
    does not permit attacker-controlled SQL structure

HTML encoding:
    safe only for the output context it is designed for

trusted principal resolver:
    may produce verified identity attributes
    only if token validation and membership conditions hold

URL validation:
    requires destination policy, redirect handling and egress enforcement
    not a generic "clean URL" guarantee
~~~

### 19.4. Không tạo framework model từ giả định thiếu chứng cứ

Giả sử một repository method tên findAuthorizedOrder. Nếu model gắn mọi kết quả của method là authorized, nhưng implementation chỉ lọc tenant ID client gửi, scanner có thể **bỏ lỗ hổng thật**.

Cần:

- Review implementation/contract và callers.
- Xác minh preconditions.
- Test positive và negative paths.
- Version API/model khi thay đổi.
- Hạn chế trusted annotations/allowlists không có owner.
- Ghi những assumptions tới assurance evidence.

## 20. Data-flow rules trong SAST toolchain

### 20.1. Các cách tiếp cận

| Cách tiếp cận | Khả năng | Giới hạn |
| --- | --- | --- |
| **Pattern matching** | Nhận diện dangerous APIs/coding patterns nhanh | Thường không theo propagation nhiều bước |
| **AST-aware rules** | Hiểu cú pháp, context và constructs | Có thể chưa theo data across calls |
| **CFG/data-flow engine** | Theo definitions, assignments, conditions | Tùy interprocedural/framework modeling |
| **Taint tracking** | Theo source–sink/sanitizer | Phụ thuộc source/sink taxonomy và trust semantics |
| **Symbolic execution** | Xây path constraints, tìm feasible path | Tốn tài nguyên, giới hạn state space |
| **Abstract interpretation** | Over-approximate program states theo domain | Precision/soundness tùy abstraction |
| **Hybrid static + runtime context** | Dùng reachability/traces/asset context | Runtime visibility có giới hạn và có thể thiếu paths |

Một sản phẩm có thể kết hợp nhiều kỹ thuật. Cần đọc khả năng thực tế của **phiên bản đang dùng** thay vì suy từ tên sản phẩm.

### 20.2. Khi chọn SAST cho một module

Câu hỏi:

- Hỗ trợ Java version và Spring Boot/framework nào?
- Scan source code, compiled bytecode hay cả hai?
- Có model Spring MVC, JPA, JDBC, Kafka, HTTP clients không?
- Có interprocedural taint analysis hay chỉ pattern?
- Có support custom source/sink/sanitizer models?
- Có giải thích trace và code locations?
- Có phân tích PR incremental và full baseline scan?
- Có rõ timeout, budget và skipped files?
- Có định dạng report máy đọc như SARIF?
- Có thể tách false positive/suppression theo rule+fingerprint?
- Có data retention/access policy phù hợp cho source code và findings?
- Có thể gắn scan results với commit/build/artifact?
- Tool có bản quyền, triển khai và quyền truy cập tương ứng với policy?

Không có một SAST tool bảo đảm mọi vulnerability class trong mọi codebase. Nên bổ sung công cụ khác theo threat: SCA, secrets scanning, IaC scanning, dynamic tests, review kiến trúc, API security tests.

### 20.3. Các công cụ phổ biến và cách hiểu đúng

Những tên công cụ thường gặp trong lĩnh vực:

- **CodeQL:** hỗ trợ chương trình truy vấn dựa trên mô hình code và data flow cho các ngôn ngữ được hỗ trợ.
- **Semgrep:** có các rule patterns và taint analysis tùy sản phẩm/engine/rule semantics.
- **SpotBugs/FindSecBugs:** kiểm tra bytecode Java theo các bug/security patterns với phạm vi phù hợp.
- **Sonar analyzers:** phân tích chất lượng và một số security rules tùy edition/language/version.
- **Compiler analyzers/IDE inspections:** hỗ trợ data-flow/nullness/quality diagnostics.

Đây là **ví dụ nhóm công cụ**, không phải khuyến nghị phiên bản hiện tại, không khẳng định mỗi công cụ đều có path sensitivity hoặc supported model giống nhau. Trước khi đưa vào baseline, xác minh tài liệu/version và kết quả trên chính codebase.

### 20.4. Rule identity và versioning

Một finding nên giữ:

- Tool và version.
- Rule/query ID và rule pack revision.
- Custom models version.
- Build mode và source revision.
- Scan coverage, exclusions và timeout.
- Finding fingerprint/correlation identity.
- Source–sink steps nếu có.
- Severity từ rule và risk-based priority do tổ chức quyết định.

Một rule update có thể làm thay số lượng findings dù code không đổi. Phải ghi **rule-set drift** khi so sánh trend.

## 21. Kiểm thử rule và model bằng fixture có kiểm soát

### 21.1. Positive testcase cho rule SQL injection

Ví dụ cố tình không an toàn trong **test fixture**:

~~~java
final class UnsafeQueryFixture {
    List<Map<String, Object>> search(
            String userInput, JdbcTemplate jdbc) {
        String sql = "SELECT * FROM orders WHERE reference = '"
                + userInput + "'";
        return jdbc.queryForList(sql);
    }
}
~~~

Mong đợi rule source–sink có thể báo nếu userInput được gắn nhãn untrusted ở entry point. Nếu fixture không mô hình source, analyzer có thể không báo dù raw query rủi ro.

### 21.2. Negative testcase cho parameter binding

~~~java
final class SafeQueryFixture {
    List<Map<String, Object>> search(
            String userInput, JdbcTemplate jdbc) {
        String sql = "SELECT * FROM orders WHERE reference = ?";
        return jdbc.queryForList(sql, userInput);
    }
}
~~~

Mong đợi rule **không báo SQL structure injection cho data parameter này**. Nhưng điều đó không kiểm tra authorization hoặc application business logic.

### 21.3. Positive testcase cho secret-to-log

~~~java
final class UnsafeSecretLoggingFixture {
    void run(SecretReader secretReader, Logger logger) {
        String credential = secretReader.loadCredential();
        logger.info("Credential: {}", credential);
    }
}
~~~

Rule cần biết loadCredential trả sensitive data, còn info là sink không cho raw credential.

### 21.4. Negative testcase cho secret logging

~~~java
final class SafeSecretLoggingFixture {
    void run(SecretReader secretReader, Logger logger) {
        String credential = secretReader.loadCredential();
        logger.info("Operation started, credentialPresent={}",
                credential != null);
        executeAuthorizedOperation(credential);
    }
}
~~~

**Giới hạn:** log Boolean trong ví dụ chỉ minh họa không ghi raw credential; trong hệ thống cụ thể, ngay cả sự hiện diện của credential có thể là sensitive metadata. Safety được quyết định bởi data classification/logging policy.

### 21.5. Những khía cạnh test rule nên có

- Direct source → sink.
- 2–5 bước propagation.
- Call/return xuyên methods.
- Field/collection/alias flows.
- Safe overwrite trước sink.
- Conditional sanitizer trên nhánh đúng.
- Sanitizer sai context không loại báo.
- Branch impossible hoặc unreachable path.
- Async/serialization boundary nếu được hỗ trợ.
- Reflection/framework callbacks có models.
- Same method gọi từ trusted/untrusted contexts.
- New API overload và dependency version.
- Timeouts/skips không được tính như rule PASS.

### 21.6. Test rule khác test ứng dụng

- **Rule test:** kiểm tra engine phát hiện hoặc không phát hiện code patterns theo kỳ vọng.
- **Security regression test:** kiểm tra application thật tuân security requirement.
- **End-to-end test:** kiểm tra integration/runtime/deployment và authorization.

Một rule test PASS không chứng minh code production an toàn; một ứng dụng test PASS không tự chứng minh SAST rule coverage đủ.

## 22. Java demo: mô hình truyền taint ở cấp giá trị

Để hiểu phép **join**, có thể xây toy model trong Java. Nó **không phân tích source code**, không parse AST/CFG và không thay SAST engine.

~~~java
import java.util.Collections;
import java.util.EnumSet;
import java.util.Set;

enum DataTag {
    UNTRUSTED,
    SECRET
}

record Fact(Set<DataTag> tags) {
    Fact {
        tags = tags.isEmpty()
                ? Collections.emptySet()
                : Collections.unmodifiableSet(EnumSet.copyOf(tags));
    }

    static Fact clean() {
        return new Fact(Collections.emptySet());
    }

    static Fact of(DataTag tag) {
        return new Fact(EnumSet.of(tag));
    }

    Fact join(Fact other) {
        EnumSet<DataTag> merged = EnumSet.noneOf(DataTag.class);
        merged.addAll(tags);
        merged.addAll(other.tags());
        return new Fact(merged);
    }

    boolean has(DataTag tag) {
        return tags.contains(tag);
    }
}

final class ToyFlowModel {
    static Fact concat(Fact left, Fact right) {
        return left.join(right);
    }

    static Fact mergeBranches(Fact branchA, Fact branchB) {
        return branchA.join(branchB);
    }

    static Fact overwriteWithTrustedConstant() {
        return Fact.clean();
    }
}
~~~

### 22.1. JUnit 5 tests cho join

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ToyFlowModelTest {
    @Test
    void untrustedInputPropagatesAcrossConcatenation() {
        Fact userInput = Fact.of(DataTag.UNTRUSTED);
        Fact constant = Fact.clean();

        Fact result = ToyFlowModel.concat(constant, userInput);

        assertTrue(result.has(DataTag.UNTRUSTED));
        assertFalse(result.has(DataTag.SECRET));
    }

    @Test
    void joinIncludesAnyTaintedBranch() {
        Fact safe = Fact.clean();
        Fact unsafe = Fact.of(DataTag.UNTRUSTED);

        Fact merged = ToyFlowModel.mergeBranches(safe, unsafe);

        assertTrue(merged.has(DataTag.UNTRUSTED));
    }

    @Test
    void separateSensitiveAndUntrustedKinds() {
        Fact merged = ToyFlowModel.concat(
                Fact.of(DataTag.SECRET),
                Fact.of(DataTag.UNTRUSTED));

        assertTrue(merged.has(DataTag.SECRET));
        assertTrue(merged.has(DataTag.UNTRUSTED));
    }

    @Test
    void trustedOverwriteCanClearOldValueFact() {
        Fact result = ToyFlowModel.overwriteWithTrustedConstant();

        assertFalse(result.has(DataTag.UNTRUSTED));
    }
}
~~~

Các test trên mô tả **semantics của join và taint kinds**, không phải các kết quả đã thực thi trong dự án. Đặc biệt overwrite chỉ an toàn nếu engine chắc chắn đã ghi đè đúng memory location và không còn alias khác.

### 22.2. Toy model bỏ sót điều gì?

- Parser/AST và CFG.
- Interprocedural calls và path constraints.
- Aliasing, heap, concurrency.
- Reflection và framework semantics.
- Actual source/sink API catalogs.
- Conditional sanitization.
- SQL/HTML/HTTP API-specific semantics.
- Exception flows.
- Runtime data classification.
- Assurance confidence.

Đây là lý do xây SAST engine chất lượng là bài toán nhiều hơn việc cộng các cờ taint.

## 23. Case study: Orders API nhiều tenant

### 23.1. Kiến trúc

Một nền tảng SaaS giả định có:

- Browser và mobile clients.
- Identity provider/API gateway.
- Orders API viết bằng Java/Spring Boot.
- PostgreSQL và Redis cache.
- Event bus/report worker.
- Payment/webhook integration.
- Secret manager và audit pipeline.
- Support console dành cho operations.

Data class minh họa: customer address/email và order/payment metadata thuộc nhóm Confidential theo tổ chức.

### 23.2. Data Flow Diagram tầng hệ thống

~~~mermaid
flowchart LR
    U["Customer / Support"] -->|"Request + token"| GW["Gateway"]
    GW --> API["Orders API"]
    API --> ID["Identity / Authorization"]
    API --> DB[("PostgreSQL")]
    API --> CACHE[("Redis")]
    API --> QUEUE[("Event Bus")]
    QUEUE --> WORK["Report Worker"]
    WORK --> FILE[("Private Export Storage")]
    API --> AUDIT[("Audit Pipeline")]
    WORK --> AUDIT
    SECRET["Secret Manager"] --> API
    PROVIDER["Payment Provider"] -->|"Webhook"| API
~~~

Các trust boundaries cần đánh giá:

- Client → API.
- Identity claims → resource authorization.
- API → database/cache.
- Producer → queue → worker.
- Workload → secret store.
- Worker → external/export storage.
- Provider → webhook receiver.
- Support operator → cross-tenant data.

### 23.3. Bốn data-flow findings minh họa

| Finding | Source | Sink | Threat |
| --- | --- | --- | --- |
| **DF-ORD-01** | HTTP query ref | Raw SQL query text | SQL injection |
| **DF-ORD-02** | Client X-Tenant-Id | Repository tenant scope | Wrong tenant authorization |
| **DF-ORD-03** | Secret store access token | Application logger | Credential disclosure |
| **DF-ORD-04** | User-supplied callback URL | HTTP client destination | SSRF |
| **DF-ORD-05** | Report queue event tenant | Worker export storage | Cross-tenant disclosure |
| **DF-ORD-06** | Customer PII fields | Telemetry exporter | Data minimization/privacy gap |
| **DF-ORD-07** | User filename | File read | Path traversal |

Không phải mọi engine SAST phát hiện đủ bảy loại. Một số yêu cầu **custom models** hoặc **dynamic/architecture tests**.

### 23.4. Mapping finding sang security requirement

| Finding | Requirement | Proposed control | Verification |
| --- | --- | --- | --- |
| DF-ORD-01 | SQL text không phụ thuộc dữ liệu untrusted | Parameterized queries | Rule test + DB integration |
| DF-ORD-02 | Tenant context đến từ verified identity | Trusted principal, resource authz | Cross-tenant API tests |
| DF-ORD-03 | Secret không ghi raw vào logs | Redaction + minimal logging | Canary secret log tests |
| DF-ORD-04 | Outbound requests chỉ tới authorized destinations | Server-side mapping, egress controls | Controlled SSRF negative tests |
| DF-ORD-05 | Export giữ verified tenant/recipient | Worker authorization and signed artifact link | Queue tamper/export tests |
| DF-ORD-06 | Telemetry chỉ nhận permitted fields | Approved schema, masking | Data-flow review + runtime sample |
| DF-ORD-07 | Chỉ đọc export thuộc user/tenant | Resource lookup and safe storage access | Path and ownership negative tests |

### 23.5. Một luồng SAST có thể rất chính xác mà vẫn chưa đủ

Giả sử engine chứng minh DF-ORD-01 đã sửa bằng parameterized SQL. Tuy vậy, nó chưa chứng minh DF-ORD-02 nếu repository vẫn lấy tenant ID từ client. Hai yêu cầu là hai security properties khác nhau.

Một conclusion đúng:

> Trong build được scan, các SQL queries thuộc phạm vi rule đã được kiểm tra về untrusted-to-raw-SQL flow theo mô hình công cụ; những đường authorization và cache/worker chưa được xác minh đầy đủ.

Một conclusion không đúng:

> Data flow analysis không còn alert, vì vậy Orders API không có security vulnerability.

### 23.6. Cross-tenant authorization cần nhiều lớp

Security invariant:

> User thuộc tenant A không được xem hoặc export tài nguyên tenant B qua API, search, cache hoặc worker, kể cả khi biết object ID.

Evidence cần:

- Trusted identity/tenant membership source.
- Code review của authorization PEP.
- Repository query/DB RLS review nếu áp dụng.
- Positive/negative API tests.
- Cache cross-tenant tests.
- Worker event provenance and authz tests.
- Role/permission revocation behavior.
- Runtime digest/config identity và protected audit.

DFA chỉ là **một trong nhiều nguồn bằng chứng** cho claim này.

## 24. Từ data-flow trace tới triage có thể giải thích

### 24.1. Một checklist 10 câu cho reviewer

1. Source có thật sự attacker-controlled hoặc sensitive trong scope?
2. Sink có thực sự dùng data theo cách nguy hiểm?
3. Propagation có đúng code/overload và type semantics?
4. Một sanitizer/validator có tồn tại không? Có hợp lệ cho sink/context?
5. Có branch/path thực thi được?
6. Có method/heap/serialization modeling gap?
7. Affected code có trong artifact triển khai?
8. Attacker cần identity, role, permission và điều kiện gì?
9. Có network/IAM/DB/data controls giảm exploit path?
10. Security requirement và business impact tương ứng là gì?

### 24.2. Triage dispositions

- **CONFIRMED:** threat path và context được xác minh có vấn đề.
- **LIKELY:** trace đáng tin nhưng còn một số giả định phải kiểm tra.
- **NEEDS_EVIDENCE:** chưa xác định được applicability/exploitability.
- **FALSE_POSITIVE:** engine báo sai trong phạm vi có evidence.
- **NOT_APPLICABLE:** component/path không nằm trong asset/version scope đã kiểm tra.
- **MITIGATED:** compensating control đã có evidence.
- **VERIFIED_FIXED:** fix được test trên build/deployment phù hợp.
- **EXCEPTION_APPROVED:** risk được chấp nhận có điều kiện.

Đừng dùng một trạng thái **SUPPRESSED** để thay mọi disposition. Suppression cần reason, owner, scope và expiry/trigger nếu phù hợp.

### 24.3. Risk-based prioritization

Xem:

- Có active exploitation hay public PoC phù hợp không?
- Source có thể kiểm soát dễ dàng từ Internet không?
- Sink có quyền đọc/sửa nhiều tenants không?
- Dữ liệu/secret nào có nguy cơ bị lộ?
- Có chain tới RCE, lateral movement hoặc control plane không?
- Có mitigation thực sự hoạt động?
- Có alert hoặc incident evidence?
- Độ chắc chắn và impact của finding?

**Tool severity chưa phải organizational priority**. Một luồng secret-to-log trong production có thể rất nghiêm trọng dù rule mặc định là Medium; một trace injection vào query test helper không deploy cần applicability review.

## 25. SARIF và lưu kết quả phân tích có cấu trúc

### 25.1. SARIF là gì?

**Static Analysis Results Interchange Format (SARIF)** là định dạng JSON chuẩn hóa để trao đổi kết quả phân tích tĩnh, với schema/version tương ứng (ví dụ SARIF 2.1.0).

Kết quả có thể chứa:

- Tool và rule information.
- Rule ID và message.
- Locations trong source.
- Related locations/code flows.
- Severity level và properties.
- Fingerprints hoặc correlation metadata.
- Artifact URIs và source references.

SARIF giúp tích hợp dashboard, IDE/PR review và lưu evidence. Tuy nhiên **không phải mọi tool hoặc mọi rule đều xuất full taint trace như nhau**.

### 25.2. Ví dụ SARIF rút gọn

~~~json
{
  "version": "2.1.0",
  "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
  "runs": [
    {
      "tool": {
        "driver": {
          "name": "IllustrativeStaticAnalyzer",
          "rules": [
            {
              "id": "SEC-SQL-001",
              "shortDescription": {
                "text": "Untrusted SQL query construction"
              }
            }
          ]
        }
      },
      "results": [
        {
          "ruleId": "SEC-SQL-001",
          "level": "error",
          "message": {
            "text": "Untrusted request value reaches a raw SQL sink"
          },
          "locations": [
            {
              "physicalLocation": {
                "artifactLocation": {
                  "uri": "src/main/java/example/OrderSearch.java"
                },
                "region": {
                  "startLine": 25
                }
              }
            }
          ]
        }
      ]
    }
  ]
}
~~~

Đây là **report minh họa**, không được sinh bởi một công cụ đã chạy. Dữ liệu thực cần mã hóa đường file/line và trace chính xác; không tự tạo confidence hoặc exploit proof từ JSON.

### 25.3. Evidence liên kết tới SARIF

Cần record bổ sung:

- Source commit.
- Build mode và module selection.
- Tool/rule pack/model versions.
- CI run ID và environment.
- Coverage/exclusions/timeout.
- SARIF artifact digest hoặc protected reference.
- Reviewer và triage decisions.
- Related security requirements, findings và retest.
- Production artifact/deployment identity nếu dùng để kết luận release.

Một SARIF file không chứa mọi thông tin cần cho assurance.

## 26. CI/CD: khi nào scan và khi nào chặn release?

### 26.1. Các điểm quét

- Trong IDE/PR để phản hồi nhanh.
- Khi merge hoặc build release.
- Periodic full baseline scan.
- Khi cập nhật SAST rules, source/sink models hoặc tool.
- Khi thêm framework/library/entry point.
- Khi tìm được class lỗi mới hoặc sau incident.
- Trước release rủi ro cao và sau remediation đáng kể.

### 26.2. Incremental scan và baseline scan

**Incremental/PR scan** giảm thời gian phản hồi, nhưng có thể:

- Không phân tích đủ code xuyên module.
- Bỏ long-standing findings không đổi trong PR.
- Mất call graph nếu build không đầy đủ.
- Không thấy rule mới phát hiện vấn đề trong code cũ.

Cần kết hợp **regular full scans và coverage monitoring**, không dùng PR scan làm toàn bộ assurance program.

### 26.3. Một pipeline conceptual

~~~mermaid
flowchart TD
    A["Source commit / PR"] --> B["Build/index + dependency modeling"]
    B --> C["Run DFA / SAST rules"]
    C --> D["Validate scan completeness and tool status"]
    D --> E{"Scanner completed with expected coverage?"}
    E -- "No" --> F["BLOCKED: investigate missing evidence"]
    E -- "Yes" --> G["Normalize findings / SARIF"]
    G --> H["Correlate new, old, and suppressed findings"]
    H --> I{"New applicable blocking findings?"}
    I -- "Yes" --> J["Fix / reviewer decision / approved exception"]
    J --> B
    I -- "No" --> K["Security tests + artifact build"]
    K --> L["Release evidence and decision"]
    L --> M["Deploy / runtime validation / periodic reassessment"]
~~~

### 26.4. Gate policy: những điều phải rõ

- Rule families nào bắt buộc cho service/risk tier?
- New findings so với baseline hay toàn bộ open findings?
- Blocker severity/priority được xác định ra sao?
- False-positive disposition có reviewer và evidence?
- Scanner timeout, crash, partial index hoặc unsupported file xử lý thế nào?
- Rule/model updates ảnh hưởng baseline ra sao?
- Suppressions có expiration và review không?
- Tool reports có integrity/access controls?
- Có emergency exception process?
- Patch verification đóng finding theo cách nào?

**Scanner failure không được tự xem như không có findings.** Báo trạng thái **NOT_RUN/BLOCKED/PARTIAL_SCAN** thay vì PASS.

### 26.5. Không biến CI thành bottleneck vô nghĩa

Cân bằng:

- PR scans nhanh cho feedback.
- Full/interprocedural scans ở build/release/periodic windows.
- Baseline/suppression governance.
- Parallelize jobs và incremental index nếu supported.
- Rule quality tests để giảm noise.
- Human triage cho path phức tạp.
- Tập trung theo threat model và asset criticality.

Một policy quá nhiều false positives có thể bị developers bỏ qua hoặc suppress hàng loạt; cải thiện rule/model quan trọng ngang bắt buộc chạy tool.

## 27. Data-flow models trong CI có thể bị lệch thế nào?

### 27.1. Framework upgrade

Nâng Spring Boot, JDBC client, logging framework hoặc HTTP client có thể:

- Đổi method overload.
- Đổi annotations/callbacks.
- Thêm wrapper classes.
- Thay bytecode structure.
- Thêm API entry points không có models.
- Thay dependency resolution.
- Làm một sanitizer model cũ không còn chính xác.

Sau upgrade, cần **rule regression fixtures** và coverage review, không chỉ chạy cùng scanner version rồi tin kết quả.

### 27.2. New language/compiler feature

Records, pattern matching, sealed types, lambdas hoặc code generation có thể làm parser/call graph thay đổi. Tool support và build mode phải tương thích.

### 27.3. Generated code và annotation processors

Nếu code generated quyết định authorization, deserialization hoặc SQL:

- Analyzer có scan generated source/bytecode không?
- Build có chạy processors trước scan?
- Có hidden download/build-time risks?
- Findings có mapping tới source ban đầu không?
- Tests có chạy trên resulting artifact không?

Không bỏ qua generated code bằng mặc định “không do người viết”.

### 27.4. Reflection và runtime configuration

Một path có thể được kích hoạt qua:

- Reflection.
- Dependency injection.
- Config profiles và feature flags.
- Plugin registry.
- Runtime class loading.
- Expression language.
- Rules từ database.

Nếu SAST không model đầy đủ, phải ghi uncertainty và dùng tests/review tương ứng.

## 28. Security claims và giới hạn kết luận

### 28.1. Cách viết claim phù hợp

Tốt:

> Với commit và modules được scan, rule SEC-SQL-001 không tìm thấy đường untrusted request input tới raw SQL execution thông qua các APIs được model trong scan này. Những dynamic native queries và worker ngoài scope chưa được xác minh.

Chưa đủ chặt:

> Hệ thống không có SQL injection.

Tốt:

> Finding về secret-to-log đã được sửa tại code path được chỉ rõ và có unit/integration log tests, với build và environment liên kết trong evidence record.

Chưa đủ chặt:

> SAST đã xanh nên không thể lộ secret.

### 28.2. Một finding được đóng khi nào?

Thông thường phải có:

1. Finding và root cause được xác nhận.
2. Patch/change reference.
3. SAST re-scan với cùng hoặc rule/model mới có giá trị.
4. Targeted security regression tests.
5. Integration/runtime tests nếu vulnerability liên quan behavior.
6. Artifact/deployment identity.
7. Những alternate paths quan trọng được xem xét.
8. Reviewer, residual risk và evidence refs.

Một finding có thể **FALSE_POSITIVE hoặc NOT_APPLICABLE**, nhưng cũng cần bằng chứng xác nhận scope, không chỉ sửa rule để alert biến mất.

### 28.3. Không có finding sau scan có nghĩa gì?

Có thể kết luận:

- Không thấy violation của những rules được chạy trong những modules được scan theo những assumptions/model/coverage đó.

Không thể kết luận:

- Không có exploit path nào.
- Không có business logic bug.
- Toàn bộ dependency graph an toàn.
- Infrastructure/network policy đúng.
- Production chạy đúng artifact.
- Không có runtime misconfiguration.
- Không có threat actor nào có thể khai thác.

## 29. Assurance: thiết kế, triển khai và vận hành

| Layer | Câu hỏi | Evidence |
| --- | --- | --- |
| **Design effectiveness** | Source/sink models và rules có phản ánh threats, requirements? | Threat model, rule design, model review, test fixtures |
| **Implementation effectiveness** | Analyzer chạy đúng trên code/build, findings được sửa? | Scan logs, SARIF, coverage, rule tests, code changes, negative tests |
| **Operating effectiveness** | Quy trình scan/triage/exception/retest có duy trì hiệu quả theo kỳ? | CI history, unresolved findings, SLA reports, post-release incidents, audit |

### 29.1. Quality của evidence

- **Relevance:** rule và trace gắn đúng security objective.
- **Completeness:** biết languages/modules/paths đã scan.
- **Correctness:** code location, source/sink semantics đáng tin.
- **Freshness:** đúng commit, tool và rule pack.
- **Traceability:** finding → decision → fix → test → release.
- **Integrity:** artifacts và logs được bảo vệ.
- **Repeatability:** scan instructions/config được ghi.
- **Independence:** reviewer có mức độc lập phù hợp.
- **Confidentiality:** không lộ secrets/PII trong logs/report.
- **Limitations:** unsupported framework, exclusions, timeouts được ghi.

### 29.2. Công cụ có thể tạo evidence mạnh nhưng vẫn cần người review

DFA thường rất mạnh với một số data-flow vulnerability classes, nhưng reviewer phải biết:

- Model có phù hợp application architecture không?
- Những paths nào không đi qua analyzer?
- Finding là potential hay đã confirmed?
- Security impact thực tế là gì?
- Điều kiện để đóng finding có đủ không?
- Có controls bù trừ nào verified?
- Những gaps nào phải escalated cho architecture review hoặc testing?

**Security assurance là đánh giá có căn cứ, không phải cộng số lượng cảnh báo hoặc dựa vào một nhãn PASS.**

## 30. Finding lifecycle và remediation

~~~mermaid
stateDiagram-v2
    [*] --> DETECTED
    DETECTED --> TRIAGE
    TRIAGE --> CONFIRMED
    TRIAGE --> NEEDS_EVIDENCE
    NEEDS_EVIDENCE --> TRIAGE
    TRIAGE --> FALSE_POSITIVE: Evidence supports invalid finding
    CONFIRMED --> PRIORITIZED
    PRIORITIZED --> FIX_IN_PROGRESS
    PRIORITIZED --> MITIGATED: Verified compensating control
    PRIORITIZED --> EXCEPTION: Authorized bounded risk
    MITIGATED --> FIX_IN_PROGRESS
    FIX_IN_PROGRESS --> READY_FOR_RETEST
    READY_FOR_RETEST --> VERIFIED_FIXED: Scan + tests + deployment evidence
    READY_FOR_RETEST --> FIX_IN_PROGRESS: Retest fails
    EXCEPTION --> TRIAGE: Expired or evidence changes
    VERIFIED_FIXED --> CLOSED
    FALSE_POSITIVE --> CLOSED
~~~

### 30.1. Remediation patterns

| Finding class | Preferred direction | Retest |
| --- | --- | --- |
| Raw SQL injection | Parameter binding; minimize DB privileges | Query/API negative tests + SAST |
| Shell injection | Avoid shell; use typed args/allowlist | Command boundary tests |
| SSRF | Fixed destinations, allowlist + egress | Redirect/DNS/internal-target negative tests |
| Path traversal | Server-managed IDs, scoped storage API | Ownership/path/symlink tests |
| XSS | Contextual output encoding/safe DOM APIs | Browser and context-specific tests |
| Secret logging | Remove raw values, redaction and log policy | Canary log/trace scans |
| Client tenant trust | Verified server-side principal/authorization | Cross-tenant API/cache/worker tests |
| Unsafe deserialization | Safe formats/types, limits, no arbitrary object construction | Untrusted input parser tests |
| Wrong secret destination | Egress allowlist, workload identity | Negative network/IAM tests |
| Missing audit | Correct event schema and reliable collection | Event delivery and retention tests |

### 30.2. Review root cause

Nếu một SQL injection pattern lặp ở nhiều services:

- Có thiếu shared safe query APIs không?
- SAST rule/model chưa phát hiện code path đó?
- Code review guidelines có bị bỏ qua?
- Build pipeline có scan đúng module?
- Đội có hiểu data vs SQL syntax boundary?
- Có unsafe helper được copy/paste?
- Cần cập nhật architecture requirement hoặc service template?
- Cần rule fixture cho library wrapper nội bộ?

Một remediation tốt có thể cần **systemic prevention**, không chỉ patch một dòng.

## 31. KPI/KRI cho data-flow analysis program

| Metric | Hỗ trợ quyết định | Giới hạn |
| --- | --- | --- |
| **Eligible code coverage** | Phần source/modules thuộc scan | Coverage theo line không bảo đảm semantic coverage |
| **Rule family coverage** | Threat classes có rules/models | Có rule không đảm bảo phát hiện mọi variant |
| **Source/sink model completeness** | Framework APIs quan trọng được model | Catalog cần cập nhật khi dependencies đổi |
| **New findings by risk tier** | New code tạo rủi ro | Tool severity có thể chưa phản ánh business impact |
| **Confirmed finding rate** | Noise/quality của rule set | Dễ bị sai nếu triage không đầy đủ |
| **False-positive rate** | Các rules cần cải thiện | Suppression thiếu căn cứ làm metric đẹp giả |
| **Rule regression test pass rate** | Models còn phát hiện fixtures | Fixtures không đại diện mọi production paths |
| **Scan completeness** | Tool chạy đủ modules, không timeout | Chạy đủ chưa chứng minh đúng |
| **Time to triage** | Khả năng xác minh finding | Phụ thuộc mức rủi ro |
| **Time to verified remediation** | Tốc độ giảm rủi ro có evidence | Khác time to merge |
| **Recurring data-flow defects** | Shared root causes còn tồn | Cần grouping theo pattern |
| **Open critical taint paths** | Tập trung rủi ro còn mở | Applicability phải được xác minh |
| **Exception age/expiry** | Risk accepted còn theo dõi | Exception không tương đương fixed |
| **Finding trace completeness** | Source/sink/call steps có đủ? | Trace có thể đúng model nhưng impossible path |
| **SAST-to-security-test linkage** | Finding có integration/negative test? | Test tồn tại chưa chắc đã chạy |
| **Post-release missed findings** | Những lỗ hổng có code path tool không báo | Phụ thuộc detection và incident visibility |

### 31.1. Ví dụ coverage

Giả sử có 20 Java modules thuộc phạm vi sản phẩm, nhưng scanner chỉ lập index và xử lý thành công 16 modules.

- **Module scan completion** = 16/20 = **80%** trên population đó.
- Không có nghĩa hệ thống an toàn 80%.
- Bốn modules chưa scan có thể chứa authorization hoặc signing service quan trọng.
- Chỉ đếm số file đã parse không cho biết dynamic reflection, frameworks, call graph và sinks được model tới mức nào.

### 31.2. Thận trọng với “zero findings”

Số findings thấp có thể vì:

- Code thực sự tốt và controls mạnh.
- Rules không phù hợp.
- Scans bị skip/timeout.
- Source/sinks không được nhận diện.
- Baseline được suppress quá rộng.
- Chỉ scan changed files.
- Critical services không được include.
- Không chạy tool sau dependency change.

Cần **coverage và quality evidence** cùng số lượng findings.

## 32. Roles và RACI

| Vai trò | Trách nhiệm |
| --- | --- |
| **AppSec/Static Analysis Owner** | Rule model, scan policy, risk-based triage, tooling strategy |
| **Developer/Application owner** | Fix code, test, explain business paths, maintain framework integrations |
| **Security architect** | Threat model, trust boundaries và source/sink policy |
| **Build/DevEx team** | CI integration, reliable scans, indexing, artifact linkage |
| **Security QA/Tester** | Negative/security regression tests và runtime verification |
| **Platform/SRE** | Deployment, network/IAM, telemetry, operations evidence |
| **Data/privacy owner** | Data classifications và authorized disclosure contexts |
| **Risk owner** | Residual risk/exception theo thẩm quyền |
| **Assurance/Auditor** | Evidence quality, scope, effectiveness conclusion |

RACI minh họa:

| Hoạt động | AppSec | Dev Owner | Build/Platform | QA | Risk Owner | Assurance |
| --- | --- | --- | --- | --- | --- | --- |
| Threat→rule requirements | **A/R** | C | C | C | I | C |
| Source/sink model review | **A/R** | R | C | C | I | C |
| Scan execution reliability | C | C | **A/R** | I | I | C |
| Finding triage | **A** | R | C | C | C | C |
| Code remediation | C | **A/R** | C | R | I | C |
| Security regression tests | R | R | C | **A/R** | I | C |
| Risk exception | C | C | C | I | **A/R** | I |
| Independent assurance conclusion | C | C | C | C | I | **A/R** |

Tổ chức thực phải điều chỉnh quyền phê duyệt, nhất là đối với việc suppress finding risk cao hoặc bỏ qua scan trong release.

## 33. Mẫu hồ sơ Data Flow Analysis Assurance

YAML sau là **mẫu minh họa**, chưa phải kết quả SAST thực tế:

~~~yaml
assessment_id: "STATIC-DFA-DEMO-005"
module: "SECURITY_SECURITY_ASSURANCE"
chapter: "Static analysis"
topic: "Data flow analysis"
service: "orders-api"
assessment_status: "DRAFT"
scope:
  language: "java"
  runtime: "spring-boot"
  environments:
    - "ci"
    - "integration"
  modules:
    - "orders-api"
    - "orders-query"
  excluded:
    - "external-payment-provider-source-code"
source_identity:
  commit: "NOT_VERIFIED"
  build_id: "NOT_VERIFIED"
  deployed_artifact_digest: null
engine:
  name: "NOT_SELECTED"
  version: "NOT_VERIFIED"
  rule_pack_version: "NOT_VERIFIED"
  custom_model_version: "NOT_VERIFIED"
  scan_completed: false
  indexed_module_count: null
  expected_module_count: 2
  excluded_files: []
  timeouts: []
source_models:
  - "spring-http-request-input"
  - "secret-store-return-value"
  - "client-controlled-tenant-header"
sink_models:
  - "raw-sql-execution"
  - "outbound-http-uri"
  - "raw-secret-logging"
  - "tenant-authorization-input"
security_requirements:
  - "SEC-SQL-001"
  - "SEC-SECRET-001"
  - "SEC-TENANT-001"
test_plan:
  - id: "T-DFA-01"
    case: "unsafe-sql-source-to-sink"
    expected: "FINDING"
    observed: "NOT_RUN"
  - id: "T-DFA-02"
    case: "parameterized-sql"
    expected: "NO_SQL_STRUCTURE_FINDING"
    observed: "NOT_RUN"
  - id: "T-DFA-03"
    case: "secret-to-logger"
    expected: "FINDING"
    observed: "NOT_RUN"
  - id: "T-DFA-04"
    case: "wrong-tenant-access"
    expected: "DENY_AT_RUNTIME"
    observed: "NOT_RUN"
findings: []
sarif_ref: null
rule_test_evidence_refs: []
runtime_test_evidence_refs: []
reviewer: null
risk_owner: "Orders Product Risk Owner"
design_effectiveness: "NOT_VERIFIED"
implementation_effectiveness: "NOT_VERIFIED"
operating_effectiveness: "NOT_VERIFIED"
assurance_conclusion: "INSUFFICIENT_EVIDENCE"
next_action: "Validate models and execute scan and security tests"
~~~

Trước khi lưu một report thật, cần thay placeholders bằng source commit, tool/rule versions, scan coverage, actual results, finding IDs, protected evidence, reviewer và deployment identity.

### 33.1. Vì sao ghi NOT_RUN và INSUFFICIENT_EVIDENCE?

Một test plan có expected result không chứng minh actual result. Một SARIF file do analyzer tạo cũng chưa nói full release đã kiểm tra. Báo cáo phải phân biệt:

- Planned.
- Executed PASS.
- Executed FAIL.
- BLOCKED/NOT_RUN.
- Partially scanned.
- Verified fixed.
- Accepted residual risk.

Không dùng kết luận **EFFECTIVE** khi chỉ mới có YAML design.

## 34. Checklist đánh giá Data flow analysis

- [ ] Có security objective, risk/threat và requirements tương ứng.
- [ ] Phân biệt data-flow static analysis với DFD kiến trúc.
- [ ] Có danh mục source kinds: untrusted, secret, PII, authorization context.
- [ ] Có sink taxonomy: SQL, shell, HTTP, file, log, response, privileged action.
- [ ] Đã ghi rõ propagation semantics qua assignment, method call, return.
- [ ] Có framework models cho entry points và sinks quan trọng.
- [ ] Sanitizers được đánh giá theo context, không theo tên hàm.
- [ ] Model tenant/role không coi client-provided value là verified context.
- [ ] Đã xét flow sensitivity và overwrites.
- [ ] Đã xét path sensitivity hoặc giới hạn của analyzer.
- [ ] Đã xét context sensitivity và method summaries.
- [ ] Có heap/alias/field sensitivity phù hợp codebase.
- [ ] Có cách xử lý reflection, generated code và native methods.
- [ ] Có phân biệt explicit và implicit information flow khi threat yêu cầu.
- [ ] Có test fixtures cho unsafe và safe patterns.
- [ ] Có negative examples chống sanitizer model quá rộng.
- [ ] Có tool/rule versions và scan configuration.
- [ ] Có inventory languages/modules và coverage/exclusions.
- [ ] Scan timeout/partial status không được báo PASS.
- [ ] Có correlation giữa source commit và artifact được test/deploy.
- [ ] Findings có source–sink trace và threat applicability review.
- [ ] Không tự coi tainted-to-sink là exploitable nếu thiếu context.
- [ ] Không tự xem absence-of-finding là absence-of-risk.
- [ ] Có priority theo exploitability, impact và compensating controls.
- [ ] Suppressions/false positives có owner, rationale và review trigger.
- [ ] Mỗi confirmed finding có control owner, fix plan và tests.
- [ ] Security regressions dùng cả positive và negative/bypass cases.
- [ ] Distributed queue/cache/worker paths được kiểm tra bổ sung.
- [ ] Những requirements không thể chứng minh bằng DFA được gắn test/review khác.
- [ ] Evidence gồm SARIF/report, logs, test run, reviewer và policy version.
- [ ] Evidence được redacted và lưu với access/integrity controls phù hợp.
- [ ] CI gate có rule cho skipped scanners và incomplete evidence.
- [ ] Có kế hoạch re-scan khi framework, source/sink model, tool hoặc code thay đổi.
- [ ] Closure dựa trên build/deployment và retest đúng scope.
- [ ] Kết luận có assumptions, exclusions, uncertainty và residual risk.

Checklist tổ chức quá trình đánh giá; không tự tạo bằng chứng ứng dụng được bảo vệ.

## 35. Bài tập thực hành

### Bài tập 1 — Tính may-taint bằng tay

Cho code:

~~~java
String a = request.getParameter("q");
String b = "constant";
String c;

if (featureEnabled) {
    c = a + b;
} else {
    c = b;
}

send(c);
~~~

Hãy xác định:

1. Source.
2. Taint facts của a, b.
3. Taint ở từng nhánh của c.
4. Join tại sink.
5. Khi nào finding thật sự là vulnerability?
6. Điều gì thay đổi nếu featureEnabled luôn false trong production?

### Bài tập 2 — Tìm sanitizer sai context

Một developer dùng HTML escaping trước khi truyền query parameter tới SQL string concatenation.

Hãy giải thích:

- Vì sao không tương đương parameter binding.
- Một rule model “escape() loại mọi taint” nguy hiểm thế nào.
- Refactor cần thiết.
- Test fixture cho unsafe và safe cases.
- Evidence nào cần trước khi đóng finding.

### Bài tập 3 — Long interprocedural path

Tạo call chain:

**Controller → Service → QueryBuilder → Repository → JDBC**.

Một request parameter xuất hiện tại controller và được nối vào raw SQL ở QueryBuilder.

Hãy:

- Vẽ CFG/data-flow trace.
- Xác định source/sink.
- Viết rule requirement.
- Xem engine cần interprocedural summaries gì.
- Liệt kê false positives/false negatives có thể xảy ra.
- Đề xuất unit/integration tests.

### Bài tập 4 — Tenant spoofing

Orders API đọc tenant ID từ X-Tenant-Id do client gửi, sau đó truyền tenant ID làm query parameter.

Hãy phân tích:

- Vì sao parameterized SQL vẫn có thể vi phạm authorization.
- DFA có thể phát hiện data origin như thế nào.
- Requirement về trusted tenant context.
- Unit/integration/cross-tenant negative tests.
- Cache/worker alternate paths.
- Evidence cho production deployment.

### Bài tập 5 — Secret leakage

Một HTTP client interceptor bật debug logging và ghi tất cả request headers. Access token được thêm trong Authorization header trước khi gọi partner.

Hãy:

- Xác định sensitive source và log sink.
- Mô hình propagation qua interceptor/framework API.
- Xem static analyzer có thực sự model client interceptor không.
- Chọn safe logging alternative.
- Viết canary test và log scan.
- Ghi giới hạn khi staging khác production logging config.

### Bài tập 6 — Triage finding không chắc chắn

SAST báo tainted URL tới HTTP client. Business owner nói host luôn thuộc allowlist, nhưng code còn automatic redirect.

Hãy quyết định:

- Evidence nào cần để xác minh allowlist?
- Redirect, DNS, IPv6 và egress ảnh hưởng thế nào?
- Cần static và dynamic tests gì?
- Khi nào chuyển CONFIRMED, FALSE_POSITIVE hoặc NEEDS_EVIDENCE?
- Ai phê duyệt residual risk?

### Bài tập 7 — Thiết kế dashboard

20 modules thuộc scope nhưng scanner xử lý 16, 3 modules có timeout và 1 không được index. Có 12 findings mới, 7 confirmed, 3 cần evidence và 2 false positive đã review.

Hãy tạo metric cho:

- Scan completeness.
- Confirmed findings.
- Incomplete scans và action owners.
- Time to triage.
- Rule quality.
- Residual risk.
- Verified closure.

Không nói “80% modules scanned nghĩa hệ thống an toàn 80%”.

## 36. Câu hỏi tự kiểm tra

1. Data flow analysis trong static analysis khác DFD ở tầng kiến trúc thế nào?
2. CFG và basic block giúp DFA xác định những gì?
3. Program point là gì? Vì sao có IN và OUT facts?
4. Reaching definitions khác taint analysis ở đâu?
5. Def-use chain có vai trò gì khi điều tra unsafe dataflow?
6. SSA và phi node giúp hợp nhất dữ liệu giữa branches thế nào?
7. Trong may-taint set analysis, tại sao thường merge bằng union?
8. Must analysis có thể dùng operator khác không? Vì sao?
9. Transfer function và GEN/KILL có nghĩa gì?
10. Vì sao một CFG có loop cần fixpoint iteration?
11. Điều kiện nào giúp một worklist analysis hội tụ?
12. Khi nào cần widening/narrowing?
13. Forward và backward data flow khác nhau thế nào?
14. Một giá trị untrusted có đồng nghĩa secret không?
15. Nêu ba sources và ba sinks điển hình trong Spring Boot.
16. Vì sao input validation và output encoding phải xét sink context?
17. Tại sao parameter binding thường an toàn hơn SQL escaping thủ công?
18. Flow-sensitive và flow-insensitive khác nhau ở ví dụ ghi đè?
19. Path-sensitive có thể giảm false positive nào?
20. Vì sao path sensitivity làm tăng chi phí tính toán?
21. Context sensitivity cần thiết khi một method được gọi từ trusted và untrusted callers thế nào?
22. Field-sensitive giúp gì với DTO chứa publicLabel và secretToken?
23. Strong update có thể gây false negative khi aliasing ra sao?
24. Reflection và Spring DI làm call graph phức tạp thế nào?
25. Method summary phải mô tả những semantics nào?
26. Vì sao one-repo static scan không chứng minh queue/worker flow toàn hệ thống?
27. Thế nào là implicit flow? Taint explicit có thể bỏ sót nó không?
28. DFA có chứng minh không có timing side channel không?
29. Một sanitizer model quá rộng dẫn tới false negative gì?
30. Vì sao hàm tên sanitize không đủ là bằng chứng an toàn?
31. Những trường hợp nào tạo false positive do path merging?
32. Scan không có finding nghĩa có thể kết luận điều gì?
33. Tại sao raw SQL parameterization không giải quyết BOLA?
34. Tenant ID trong client header có được tin như verified identity không?
35. SSRF có thể xảy ra dù URL ban đầu qua allowlist vì sao?
36. Vì sao path.normalize và startsWith chưa loại hết symlink race?
37. SAST rule test khác API security regression test thế nào?
38. SARIF có lưu được những loại thông tin nào?
39. Vì sao cần lưu commit, rule pack và model version?
40. PR incremental scan có thể bỏ lỡ lỗ hổng trong code không đổi thế nào?
41. Vì sao scan tool timeout không được coi là PASS?
42. CVSS/severity của tool có đủ làm organizational priority không?
43. Khi nào một finding được gắn FALSE_POSITIVE?
44. Cần những evidence nào để đóng một injection finding?
45. Design, implementation và operating effectiveness khác nhau thế nào?
46. Vì sao một static trace dài chưa chắc có exploit path thực?
47. Nếu SAST không model custom repository wrapper, cần làm gì?
48. KPI zero findings có thể bị sai lệch bởi yếu tố nào?
49. Những security claims nào phải dùng runtime verification bổ sung?
50. Khi module nâng framework/DI library, cần đánh giá lại rule models như thế nào?

## 37. Tổng kết

**Data flow analysis** là phương pháp phân tích tĩnh suy ra facts về nguồn, giá trị và cách dữ liệu lan truyền qua instructions, branches, function calls và memory state. Nền tảng của nó gồm **CFG, program points, definitions/uses, transfer functions, merge operators, lattice và fixpoint computation**. Trong bảo mật, **taint analysis** dùng DFA để mô hình hóa **sources, propagations, sinks, sanitizers và trust boundaries**, từ đó phát hiện ứng viên của SQL injection, SSRF, path traversal, unsafe output, lộ secrets/PII và một số vấn đề về nguồn dữ liệu dùng trong authorization.

Chất lượng DFA phụ thuộc **flow/path/context/field sensitivity, interprocedural models, alias/heap analysis, framework coverage và giới hạn chi phí tính toán**. Một trace có thể chứa false positive; một scan không có findings vẫn có thể có false negative, đặc biệt với **reflection, distributed flows, business logic và runtime policies**. Các findings phải được triage bằng **attacker control, exploitability, data classification, asset exposure và security requirements**, rồi gắn **owner, remediation, targeted negative tests và retest**.

Trong module **SECURITY_SECURITY_ASSURANCE**, DFA có giá trị khi tạo được **evidence chain từ threat/requirement → static rule/model → scan version/result → finding/trace → fix → security test → deployed artifact → assurance conclusion**. Không đánh đồng scanner PASS với hệ thống an toàn, không xem approved exception là fix, và luôn ghi **phạm vi, exclusions, công cụ, cấu hình, độ tin cậy và residual risk**. Khi code, framework, trust boundary hoặc deployment thay đổi, mô hình và bằng chứng DFA cần được đánh giá lại.
