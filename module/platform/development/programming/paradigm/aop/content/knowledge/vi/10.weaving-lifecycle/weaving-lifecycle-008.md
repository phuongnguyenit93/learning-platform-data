# So sánh độ bao phủ, chi phí và độ phức tạp vận hành theo thời điểm dệt AOP

## 1. Vì sao thời điểm dệt ảnh hưởng đến thiết kế?

Trong **Aspect-Oriented Programming (AOP)**, việc dùng **pointcut** để chọn **join point** và dùng **advice** để bổ sung hành vi mới chỉ là phần mô tả logic. Một phần quan trọng không kém là **cách và thời điểm** hệ thống gắn hành vi đó vào chương trình: lúc biên dịch, sau biên dịch, lúc class được nạp, hay khi một lời gọi đi qua proxy/interceptor ở runtime.

Các chiến lược này có thể tạo ra cùng một trace đơn giản:

~~~text
before
core: execute
after
~~~

Nhưng chúng **không tương đương** về các đặc tính quan trọng:

- **Độ bao phủ:** có chặn được những lời gọi nào, method body nào, code thư viện nào, class loader nào; có theo được gọi nội bộ, constructor và field access không?
- **Chi phí:** phải trả bao nhiêu cho việc dệt lúc build, biến đổi class khi load, tạo proxy, kiểm tra điều kiện động, dispatch lời gọi, lưu bytecode mới và ghi log?
- **Độ phức tạp vận hành:** cần build/deploy gì, có dễ tìm lỗi thiếu advice không, có kiểm soát class loader hoặc agent không, cập nhật/rollback có an toàn không?
- **Tính đúng đắn:** có bảo toàn return value, exception, locking, thứ tự advice và số lần target chạy không?

**Đề bài ở đây không phải tìm ra một kỹ thuật “nhanh nhất” hay “mạnh nhất” tuyệt đối.** Mục tiêu là biết đo và cân nhắc các đánh đổi theo nhu cầu cụ thể. Độ bao phủ phụ thuộc **join point model** và phạm vi instrument của **công cụ AOP được chọn**, không chỉ nhãn “compile-time” hay “runtime”.

## 2. Phân loại cho đúng trước khi so sánh

Có hai trục phân loại khác nhau:

**Trục A — Thời điểm liên kết hành vi**

1. **Compile-time weaving (CTW):** gắn logic AOP trong hoặc trước quá trình biên dịch chương trình.
2. **Post-compile/binary weaving (PCW):** nhận artifact đã biên dịch, biến đổi thành artifact có hành vi AOP trước khi chạy.
3. **Load-time weaving (LTW):** biến đổi bytecode khi class được định nghĩa trong runtime, dựa trên bộ dệt hoặc transformer đã đăng ký.
4. **Runtime interception/wiring:** tạo proxy/decorator hoặc dispatcher/interceptor chain để lời gọi đi qua nó lúc runtime.

**Trục B — Lớp biểu diễn chịu tác động**

- Source code hoặc abstract syntax tree (AST).
- Intermediate representation (IR) của compiler.
- Bytecode/class file hoặc artifact biên dịch tương đương.
- Object graph, proxy reference, call route hoặc invocation chain.

**Quan trọng:** load-time weaving thường vẫn biến đổi **bytecode**, còn runtime proxy có thể **không sửa bytecode của target**. Vì thế không nên định nghĩa hai thuật ngữ ấy như hai nơi chèn mã hoàn toàn ngang hàng.

Một ngôn ngữ AOP cụ thể có thể hỗ trợ nhiều thời điểm. Hơn nữa, một dự án có thể cùng lúc dùng binary weaving cho một concern và proxy cho concern khác. Sự kết hợp đó là hợp lệ nhưng gây rủi ro advice bị áp dụng chồng nhau.

## 3. Cùng một yêu cầu, bốn con đường áp dụng

Giả sử cần ghi nhận trước/sau mọi lần thực thi của một thao tác nghiệp vụ.

~~~text
                        ASPECT
              pointcut + before/after advice
                          │
             ┌────────────┼─────────────┬─────────────┐
             ▼            ▼             ▼             ▼
        COMPILE TIME   POST COMPILE   LOAD TIME    RUNTIME ROUTE
             │            │             │             │
        Compiler tạo   Weaver sửa    Transformer   Proxy / decorator
        mã đã dệt      class/JAR     sửa class khi intercept lời gọi
             │            │          define         │
             └────────────┴─────────────┴─────────────┘
                          │
                          ▼
                  Chạy chương trình thật
                          │
                     Join point khớp?
                          │
                  ┌───────┴───────┐
                 Không            Có
                  │                │
                  ▼                ▼
             Không chạy         Advice chạy
             advice            ở lượt đó
~~~

**Weave xong không có nghĩa advice đã chạy.** Compile có thể kết thúc hôm nay, class được nạp ngày mai, và join point chỉ được thực thi khi một request xuất hiện. Tương tự, proxy có thể được tạo mà không hề có một cuộc gọi nào đi qua nó.

Khi đối chiếu các thời điểm dệt, phải đánh giá riêng **thời điểm tạo khả năng can thiệp** và **thời điểm trả chi phí của mỗi invocation**.

## 4. Định nghĩa “độ bao phủ” một cách có thể kiểm thử

Độ bao phủ AOP không chỉ là tỷ lệ method có log. Nên tách ít nhất năm chiều:

| Chiều | Câu hỏi |
|---|---|
| **Loại join point** | Method call, method execution, constructor, field get/set, static initialization có được hỗ trợ không? |
| **Phạm vi code** | Chỉ module mình build, cả thư viện binary, code từ nhiều loader, code sinh động? |
| **Đường lời gọi** | Caller gọi qua proxy hay trực tiếp target? Self-invocation có được nhận diện? |
| **Quan hệ kiểu/đa hình** | Interface, superclass, subclass override, method kế thừa và bridge method có được chọn đúng? |
| **Điều kiện runtime** | Target subtype, arguments, annotation, control-flow có khiến lần này khớp nhưng lần khác không? |

Một cách đo hữu ích:

~~~text
Coverage theo yêu cầu =
    số tình huống bắt buộc áp dụng advice đã được xác nhận
    -----------------------------------------------------
    tổng số tình huống bắt buộc theo đặc tả
~~~

Đây là **chỉ số kiểm thử do dự án định nghĩa**, không phải một tỷ lệ có sẵn mà engine AOP tự cung cấp. Mẫu số phải nêu rõ các **trường hợp cần được bảo vệ/quan sát**. Đừng gộp test case vào một phép đếm method rồi tuyên bố đạt đủ mọi đường gọi.

### 4.1. Độ bao phủ “phải chạy” và “không được chạy”

Một pointcut quá rộng cũng là lỗi. Có thể dùng hai phép kiểm:

- **Recall có ý nghĩa nghiệp vụ:** mọi đường bắt buộc đều được advice áp dụng.
- **Precision có ý nghĩa nghiệp vụ:** các đường ngoài phạm vi không bị advice áp dụng.

Ví dụ một policy chỉ dành cho public API nhưng vô tình log mọi helper nội bộ có thể làm tăng chi phí, lộ dữ liệu hoặc tạo advice recursion. Vì vậy nên có cả **positive tests** và **negative tests**.

### 4.2. Bản đồ bao phủ mới có giá trị

Một danh sách “100% methods woven” không đủ nếu caller đang chạy các class được nạp bởi loader khác, hoặc một proxy chỉ được dùng ở một nhánh. Cần mô tả **những join point thực tế** và **đường code đi đến chúng**.

## 5. Bảng so sánh tổng quan bốn chiến lược

Bảng dưới thể hiện **xu hướng thường gặp, có điều kiện**, không phải xếp hạng tuyệt đối theo một sản phẩm.

| Tiêu chí | Compile-time | Post-compile binary | Load-time | Runtime proxy/interceptor |
|---|---|---|---|---|
| **Đầu vào chính** | Source/AST/IR + aspect | Class/JAR + aspect | Class bytes + transformer | Target/interface + handler |
| **Đầu ra chính** | Binary sinh từ mã đã dệt | Binary woven | Class definition đã biến đổi | Proxy/reference/route |
| **Chi phí setup** | Lúc build | Lúc build/release | Lúc class loading | Khi tạo proxy/chain |
| **Chi phí runtime** | Code advice và điều kiện động nếu có | Tương tự binary đã dệt | Code advice sau biến đổi | Handler/delegation và code advice |
| **Sửa target body được không?** | Tùy compiler/weaver | Có nếu engine hỗ trợ | Có nếu transform hợp lệ | Thường không cần sửa body |
| **Self-invocation** | Có thể thấy nếu weave execution liên quan | Có thể nếu weave execution | Có thể nếu weave execution | Có thể bypass proxy |
| **Thư viện chỉ có binary** | Không tự có source; tùy pipeline | Có thể weave binary | Có thể transform khi load | Có thể bọc public boundary |
| **Constructor/field/static** | Tùy join point model | Tùy engine | Tùy engine | Proxy interface không tự hỗ trợ |
| **Artifact dễ kiểm tra trước deploy** | Thường có | Có woven binary cụ thể | Không nhất thiết có file woven trên đĩa | Cần kiểm tra object wiring |
| **Vận hành phức tạp nổi bật** | Compiler integration, rebuild | Artifact provenance/reweave | Agent, loader, startup, module | Reference routing, bypass, chain order |
| **Rollback điển hình** | Redeploy bản build trước | Redeploy woven artifact trước | Thay config/agent rồi restart hoặc cơ chế hợp lệ | Cấp lại reference/chain theo lifecycle |

Thứ tự nào “tốt hơn” phụ thuộc loại join point cần chọn, ràng buộc triển khai và mức rủi ro chấp nhận được. Không chọn chỉ theo số cột “Có”.

## 6. Compile-time weaving: độ bao phủ, chi phí và vận hành

### 6.1. Độ bao phủ

Một compiler-integrated weaver có thể dùng source/AST/IR và type information để nhận diện join point trong **tập code đi qua compiler pipeline đó**. Nếu compiler và ngôn ngữ AOP hỗ trợ method execution hoặc call-site instrumentation, điểm trong tập compile có thể được dệt trước khi deploy.

Thế mạnh:

- Rõ **đầu vào được build** và artifact đầu ra; phù hợp với dự án có quản lý nguồn.
- Có thể tận dụng semantic information mà compiler cung cấp.
- Có thể tạo artifact đã có hành vi, ít phụ thuộc vào agent runtime.

Giới hạn:

- Code trong thư viện **chỉ có binary** thường không tự nằm trong source transform; một compiler có hỗ trợ binary weaving riêng mới có thể xử lý kiểu đó.
- Class sinh ra hoặc được nạp theo đường nằm ngoài pipeline có thể không được bao phủ.
- Chữ ký thay đổi, class chuyển package hoặc thêm override có thể làm pointcut match khác sau rebuild.
- Khả năng chặn private/final/static/constructor tùy compiler-weaver; **không thể suy từ thời điểm compile**.

### 6.2. Chi phí

Một phần chi phí dịch chuyển sang build:

- Phân tích type hierarchy, matching pointcuts.
- Biến đổi source/IR và sinh helper code.
- Chạy compile, tạo artifact và verify.
- Build cache/rebuild khi code hoặc aspect thay đổi.

Ở runtime **vẫn có chi phí advice và điều kiện runtime**. Nếu advice làm I/O hoặc một pointcut có dynamic predicate, code đã dệt không làm tác vụ ấy trở nên miễn phí.

### 6.3. Độ phức tạp vận hành

- Cần toolchain compiler/weaver version tương thích.
- Quy trình kiểm tra generated source, warnings, build cache và source mapping.
- Artifact phải được tạo lại khi aspect rule đổi.
- Deploy/rollback có thể rõ ràng thông qua các bản build bất biến.
- Nếu dùng compiler extension đặc thù, nâng phiên bản compiler có thể làm build fail.

**Phù hợp khi:** kiểm soát được nguồn và pipeline, muốn artifact có thể tái lập và có thể chấp nhận rebuild/redeploy cho thay đổi aspect.

## 7. Post-compile weaving: độ bao phủ, chi phí và vận hành

Post-compile weaving nhận **artifact đã biên dịch** rồi tạo một **artifact woven**:

~~~text
Source → compiler → Original.class/JAR
                               │
                               ▼
                   Binary weaver + aspect
                               │
                               ▼
                     Woven.class/JAR
                               │
                               ▼
                              Runtime
~~~

### 7.1. Độ bao phủ

Thường hữu ích khi **không có source của thư viện** nhưng có binary hợp lệ mà weaver được phép instrument. Có thể lựa chọn method execution hoặc call sites trong những class/JAR được đưa vào weave, tùy ngôn ngữ AOP.

Tuy nhiên:

- Không phải mọi binary đều được phép hoặc có thể được biến đổi tùy chữ ký số, license, deployment policy và engine.
- Nếu chỉ weave target nhưng pointcut muốn chọn **call sites trong các caller ngoài tập binary**, những vị trí đó vẫn có thể không được chạm tới.
- Nếu một subclass binary mới không được đưa vào pipeline, execution override của nó có thể bị bỏ sót.
- Class file phiên bản không tương thích hoặc có những instruction engine không hiểu có thể gây lỗi.

### 7.2. Chi phí

Trả thêm bước build/release:

- Đọc/giải mã class/JAR.
- Match điểm, sinh instruction hoặc helper.
- Cập nhật class metadata, stack map frames, exception handlers nếu cần.
- Kiểm tra class-file correctness, test artifact sau dệt.
- Lưu cả artifact trước và sau weaving nếu cần đối chiếu.

Runtime đã nhận một artifact có code AOP, nhưng vẫn phải chạy advice, object allocation và runtime tests nếu pointcut đòi hỏi.

### 7.3. Độ phức tạp vận hành

Điểm khó quan trọng nhất là **provenance**:

- Binary nào đã được weave, version và checksum ra sao?
- Pipeline đóng gói **bản woven** hay vô tình lấy bản chưa weave?
- Weaver được chạy một lần hay bị chạy lặp lên output trước?
- Có thể tái tạo cùng một output từ cùng input/config không?
- Khi rollback, có khôi phục cả artifact và version aspect tương thích không?

Một build báo weave thành công nhưng deploy classpath vẫn trỏ đến binary cũ là lỗi vận hành, không phải lỗi của advice.

**Phù hợp khi:** cần tác động vào binary, muốn phát hành artifact woven cụ thể và có kiểm soát build/deploy chặt.

## 8. Load-time weaving: độ bao phủ, chi phí và vận hành

Một runtime có thể đăng ký **class-file transformer** để xử lý bytecode trước khi JVM **define class**.

~~~text
Original JAR trên đĩa
        │
        ▼
Class loader chuẩn bị define
        │
        ▼
Transformer nhận class bytes
        │
        ▼
Woven class definition trong JVM
        │
        ▼
Method/điểm đã weave được thực thi sau đó
~~~

### 8.1. Độ bao phủ

Điểm mạnh tiềm năng: có thể instrument các class **được nạp sau khi cấu hình weaving có hiệu lực**, kể cả một số thư viện mà ứng dụng chỉ có binary, nếu engine/agent/class loader cho phép.

Nhưng coverage cần kiểm tra từng đường:

- Transformer có chạy với **class loader** đó không?
- Có class nào đã được define **trước lúc agent/transformer đăng ký** không?
- Module và quyền truy cập có cho phép code helper hoạt động không?
- Một class được nạp lại qua loader khác có nhận cùng aspect không?
- Class được exclude vì package/loader hoặc không match pointcut không?

Một engine có hỗ trợ **retransform/redefine** không mặc định được sửa mọi thành phần cấu trúc của class đã nạp; giới hạn của JVM/API phải được kiểm tra.

### 8.2. Chi phí

Chi phí có thể chuyển từ build sang **startup/class loading**:

- Đăng ký, khởi tạo agent và transformer.
- Phân tích/biến đổi mỗi class được chọn.
- Verify, link và load những helper liên quan.
- Thời gian và bộ nhớ tạm cho byte arrays/class metadata.
- Khả năng ảnh hưởng cold-start và thời điểm một module được sử dụng lần đầu.

**Lưu ý:** class loading thường diễn ra trước một số lời gọi, không phải transformer chạy lại cho mỗi invocation. Sau khi class được định nghĩa với code đã weave, lời gọi method thông thường thực thi code đó; không tự trả lại “chi phí biến đổi bytecode” ở mọi lần gọi.

### 8.3. Độ phức tạp vận hành

- Cấu hình agent/transformer phải được cài đúng trước class load cần thiết.
- Độ khó quan sát cao hơn vì binary trên đĩa **có thể không phải bytes mà JVM đã dùng**.
- Nhiều class loader và nhiều transformer có thể có thứ tự ảnh hưởng kết quả.
- Log trong chính quá trình nạp class có thể gây reentrancy nếu helper lại kích hoạt class loading.
- Thay cấu hình có thể yêu cầu restart hoặc cơ chế retransform hợp lệ; không có bảo đảm mọi class đang sống lập tức đổi.

**Phù hợp khi:** cần tác động lên class lúc runtime nạp mà không muốn phát hành một bản JAR woven riêng, đồng thời đội ngũ đủ khả năng quan sát và vận hành class loading/agent.

## 9. Runtime proxy/interception: độ bao phủ, chi phí và vận hành

Proxy, decorator và interceptor chain tạo một **đường gọi được bao ngoài**:

~~~text
Caller → Proxy/interceptor → Target
            │                 │
            ├─ before         │
            ├─ invoke ───────►│
            └─ after ◄────────┘
~~~

### 9.1. Độ bao phủ

Độ bao phủ phụ thuộc **caller có sử dụng đúng reference proxy** và **method có được proxy expose/intercept**.

Điểm mạnh:

- Dễ giới hạn chính sách tại boundary/API đã định nghĩa.
- Có thể bọc implementation mà không sửa class gốc.
- Có thể chọn interceptor chain khác nhau cho các object hoặc request theo thiết kế.

Giới hạn:

- **Bypass:** caller cầm target gốc có thể gọi thẳng.
- **Self-invocation:** target tự gọi method khác trên chính nó thường không đi lại qua proxy.
- **Interface proxy:** chỉ những method thuộc interface được proxy implement mới có đường dispatch handler tương ứng.
- **Static/private/final/constructor/field:** cần xem loại proxy hoặc engine cụ thể, không coi mọi khả năng đều tồn tại.
- **Call-site context:** một proxy nhận method call nhưng không tự biết chính xác source location của mọi caller như một call-site weaver có thể biết.

### 9.2. Chi phí

Chi phí phân bố vào:

- Tạo proxy/decorator và lắp interceptor chain.
- Dispatch mỗi invocation qua tầng bao.
- Reflection hoặc method-handle call nếu engine dùng; boxing/array allocation ở một số API.
- Runtime pointcut checks nếu có.
- Chi phí code advice thực sự chạy.

Một proxy chỉ có một interceptor không có cùng overhead với một chain nhiều tầng, nhiều dynamic predicate và logging network. JIT có thể tối ưu nhiều đường gọi; không đo thì không có cơ sở kết luận chênh lệch bao nhiêu.

### 9.3. Độ phức tạp vận hành

- Phải kiểm soát **object creation/wiring** để caller nhận đúng proxy.
- Cần biết vòng đời proxy so với target.
- Nếu policy quan trọng, phải tìm đường giữ target gốc hoặc self-call ngoài ý muốn.
- Thứ tự nhiều interceptor phải được đặc tả và test.
- Thay config có thể cần dựng chain/proxy mới hoặc một cơ chế dynamic refresh được engine hỗ trợ.
- Dễ debug một số boundary, nhưng lỗi coverage có thể ẩn vì code target vẫn chạy đúng, chỉ **thiếu advice**.

**Phù hợp khi:** concern ở public/service boundary rõ, object graph được quản lý và không yêu cầu quan sát mọi điểm bên trong implementation.

## 10. So sánh riêng từng chiều bao phủ

### 10.1. Khi cần chặn method execution ở mọi caller

Một execution weaver instrument trực tiếp thân method có khả năng bắt lời gọi đến thân ấy từ các caller khác nhau, kể cả caller không biết aspect, **nếu** method thực thi đúng thân đã weave.

Proxy không có bảo đảm tương ứng nếu một caller giữ target gốc. Vì vậy, trong yêu cầu “mọi đường vào implementation phải qua kiểm tra”, nên xem xét trực tiếp độ bao phủ mà execution weaving thực sự đạt được hoặc ràng buộc kiến trúc khiến mọi caller chỉ dùng proxy.

### 10.2. Khi cần chặn đúng call site

Một call join point chọn **vị trí phát lời gọi**, có thể phân biệt một caller trong module A với caller trong module B. Để có bao phủ, **caller code** liên quan phải được instrument. Weave chỉ mỗi target body không đương nhiên biết call site nào đã phát lệnh.

Proxy thường biết invocation đến qua object đại diện nhưng không tự sở hữu toàn bộ thông tin lexical source location. Nếu chính sách phụ thuộc caller/source code, cần đánh giá khả năng hỗ trợ call join point của engine cụ thể.

### 10.3. Khi có lời gọi nội bộ

~~~java
class Task {
    void outer() { inner(); }
    void inner() { /* công việc */ }
}
~~~

Đoạn này chỉ minh họa. Nếu caller bên ngoài gọi proxy.outer, proxy có thể chặn outer; nhưng bên trong target, **inner()** không tự đi qua proxy.

Một weaver tại **execution của inner** có thể quan sát inner nếu method được instrument và pointcut khớp. Không nên áp giới hạn self-invocation của proxy thành định luật chung của AOP.

### 10.4. Với override và subtype

~~~java
BaseService service = new FastService();
service.execute();
~~~

Đây là minh họa cần định nghĩa hai class. Compiler có thể nhìn chữ ký BaseService tại call site; runtime dispatch tới override FastService.execute. Vì thế:

- Call pointcut có thể xét chữ ký ở caller.
- Execution pointcut có thể xét thân FastService.
- Dynamic target condition có thể xét kiểu thực của object.
- Weaving chỉ ở Base nhưng không ở override FastService có thể không đáp ứng yêu cầu.

Cần test cả subclass **kế thừa không override**, subclass **có override**, interface implementation và những method compiler sinh như bridge nếu công cụ ở mức bytecode liên quan.

### 10.5. Static, private, final và constructor

Không thể xếp hạng “CTW luôn chặn được” hoặc “LTW luôn chặn được”. Khả năng phụ thuộc ngôn ngữ AOP và join point model.

- **Static:** không có receiver instance theo nghĩa method instance.
- **Private:** không lộ qua interface proxy thông thường; một bytecode weaver có thể hỗ trợ execution tùy engine.
- **Final:** không thể override bằng subclass proxy; một bytecode weaver can thiệp trực tiếp có ràng buộc khác.
- **Constructor:** một số weaver có constructor call/execution join points; interface proxy không tự chặn quá trình khởi tạo target.
- **Field get/set:** có thể là join point ở mô hình weaving phong phú; method-only proxy không tự quan sát trực tiếp field access.

### 10.6. Class loader và code thư viện

Thời điểm dệt càng muộn **không tự khiến độ bao phủ rộng hơn**. Load-time engine có thể nhìn nhiều class runtime nhưng cũng có thể bị giới hạn ở loader, module và registration timing. Một post-compile binary weaver được cấu hình đầy đủ có thể có phạm vi thư viện rõ hơn, nhưng sẽ bỏ qua code sinh mới sau build nếu không có bước phù hợp.

Độ bao phủ phải chứng minh bằng **tập class/call sites được instrument** cộng **runtime invocation tests**, không phải tên pha.

## 11. Mô hình chi phí ba pha

Để so sánh công bằng, hãy tách chi phí thành:

**A. Chi phí tạo artifact/configuration**

- Build/compile, parse pointcut, match type hierarchy.
- Binary transformation và validation.
- Tạo proxy và interceptor chain.

**B. Chi phí khởi động / nạp class**

- Agent initialization và transformer work.
- Class loading/verification/linking và helper initialization.
- Khởi tạo proxy/graph nếu thực hiện ở startup.

**C. Chi phí ở mỗi lời gọi**

- Dynamic type/args/control-flow checks.
- Interceptor dispatch/delegation hoặc woven advice call.
- Advice body (logging, trace export, security checks, metrics).
- Side effects và synchronization.

Một mô hình tổng chi phí hữu ích:

~~~text
TotalCost ≈ BuildCost
          + NumberOfStarts × StartupCost
          + NumberOfInvocations × AverageInvocationCost
          + OperationalCost
~~~

Đây là **mô hình định tính**, không phải công thức đo chính xác mọi chi phí tài nguyên bằng cùng một đơn vị. Build time, latency, CPU, memory, dung lượng artifact và chi phí vận hành không thể tự cộng thành một số tiền nếu chưa có cách quy đổi.

### 11.1. Dịch chuyển chi phí không có nghĩa xóa chi phí

- CTW/PCW có thể dồn chi phí transformation vào build, nhưng advice runtime vẫn chạy.
- LTW có thể tăng startup/class-load time, nhưng **không phải một lượt transform cho mỗi method call**.
- Proxy có thể có chi phí tạo object khi dựng graph, và chi phí invocation routing sau đó.
- Logging I/O nhiều khi áp đảo chi phí dispatch; khi đó tranh luận “proxy hay bytecode nhanh hơn vài nano giây” có thể không liên quan đến nút thắt thật.

### 11.2. Chi phí cold-start và steady-state khác nhau

Một dịch vụ sống nhiều ngày có thể chấp nhận thêm thời gian khởi động để đổi lấy behavior cần thiết. Một workload serverless/chạy ngắn và khởi tạo nhiều lần có thể nhạy cảm với load-time instrumentation hoặc xây dựng object graph.

Ngược lại, một method được gọi hàng triệu lượt có thể đáng đo chi phí dispatch tại steady-state. Không có một phép đo startup nào đại diện cho steady-state, và ngược lại.

## 12. Benchmark như thế nào để không tự đánh lừa?

Đừng đưa ra bảng nano giây hay phần trăm “độ chậm” khi chưa có cùng môi trường kiểm chứng. Khi đo thực tế:

1. Giữ **cùng chức năng target**, cùng input và cùng hành vi advice ở các kịch bản.
2. Dùng **baseline không advice**, rồi đo từng cơ chế với policy tương đương.
3. Tách **thời gian build**, **startup**, **class-load**, **steady-state throughput**, **latency p50/p95/p99**, **allocation** và **memory footprint**.
4. Với Java, dùng công cụ microbenchmark phù hợp như **JMH** khi cần đo overhead nhỏ, có warmup, fork, công cụ tránh dead-code elimination và kiểm soát JIT.
5. Tránh dùng vòng lặp tự đo một lần trong main rồi kết luận hiệu năng tương đối của engine.
6. Lặp trên các cấu hình có **ít/nhiều join point**, **ít/nhiều advice**, có/không dynamic predicate.
7. Tách thí nghiệm advice rỗng/nhẹ và advice có I/O thật.
8. Kiểm tra cả GC, object allocation, logging queue/backpressure và contention.
9. Đo trên **đúng JDK, phần cứng, toolchain và workload** của hệ thống mục tiêu.
10. Báo cáo sai số, độ biến động và trade-off thay vì chọn một giá trị nhanh nhất.

**Không được dùng JDK proxy demo phần sau để chứng minh một kỹ thuật nhanh hơn kỹ thuật khác.** Demo chỉ xác minh phạm vi interception và số lần gọi; so sánh performance cần benchmark riêng.

## 13. Độ phức tạp vận hành: phải quản lý những gì?

### 13.1. Build và phát hành

- CTW cần compiler integration, generated code consistency, cache invalidation và rebuild khi thay aspect.
- PCW cần lưu original/woven artifact, kiểm tra binary provenance, ngăn double weaving.
- LTW cần agent/transformer có mặt đúng lúc, class loader/module compatibility.
- Proxy cần factory, wiring và lifecycle kiểm soát reference.

### 13.2. Chẩn đoán sự cố

“Không có log advice” có thể do:

- Pointcut không match.
- Join point chưa thực thi.
- Class chưa được weave.
- Binary chưa weave được đóng gói nhầm.
- Class được định nghĩa trước transformer.
- Class loader ngoài scope.
- Caller bypass proxy.
- Dynamic predicate false.
- Around advice ở tầng ngoài không gọi proceed.
- Log bị drop hoặc exporter lỗi.

Mỗi cơ chế có **bằng chứng chẩn đoán khác nhau**. Nếu dùng proxy, kiểm tra reference; nếu dùng LTW, kiểm tra loader/agent; nếu dùng binary weaving, kiểm tra artifact chạy thật.

### 13.3. Rollback và incident response

- Với artifact woven: rollback bằng **artifact version đã xác minh**.
- Với LTW: có thể cần đổi agent/config và restart, hoặc cơ chế retransform được hỗ trợ.
- Với proxy: có thể thay interceptor chain/wiring theo lifecycle, nhưng caller giữ proxy cũ có thể chưa cập nhật.
- Với source generation: cần build/deploy lại khi rule đã đi vào binary.

Một hệ thống cần yêu cầu rollback nhanh có thể ưu tiên cách có **versioning và khả năng chứng minh trạng thái runtime** tốt nhất cho môi trường đó.

### 13.4. Quan sát và giám sát

Nên thu các tín hiệu:

- Số join point thực sự được chọn và số advice invocations.
- Số target invocations so với advice, đặc biệt khi retry/short-circuit.
- Build/weave warnings hoặc runtime transformer errors.
- Class loader/class-definition diagnostic khi cần.
- Proxy routing anomalies hoặc invocation bypass trong test.
- Startup time, class-loading latency, allocation và CPU overhead.
- Số log/trace dropped nếu dùng exporter bất đồng bộ.

**Số advice invocation không tự bằng số nghiệp vụ.** Một request có thể tạo nhiều join point hoặc nhiều retries.

## 14. Java 17 runnable: chứng minh giới hạn coverage của runtime proxy

Chương trình độc lập sau dùng **JDK dynamic proxy**. Mục tiêu là phân biệt:

- Lời gọi trực tiếp target.
- Lời gọi qua proxy.
- Lời gọi nội bộ từ target method đến method khác trên chính target.
- Lời gọi riêng đến method đó qua proxy.
- Số lượt interceptor so với số lượt method body thực chạy.

Nó **không triển khai bytecode weaving**. Vì vậy không dùng ví dụ để suy số liệu overhead hoặc khả năng constructor/field join points của các engine khác.

Tạo file **CoverageBoundaryDemo.java**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;

public class CoverageBoundaryDemo {
    interface Service {
        int process(int value);
        void internalStep();
    }

    static final class Core implements Service {
        int processCalls;
        int stepCalls;

        @Override
        public int process(int value) {
            processCalls++;
            System.out.println("core: process " + value);
            internalStep();
            return value * 2;
        }

        @Override
        public void internalStep() {
            stepCalls++;
            System.out.println("core: step");
        }
    }

    static Service proxy(Service target, AtomicInteger interceptions) {
        return (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[]{Service.class},
                (instance, method, args) -> {
                    interceptions.incrementAndGet();
                    System.out.println("proxy: before " + method.getName());
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException error) {
                        throw error.getCause();
                    } finally {
                        System.out.println("proxy: exit " + method.getName());
                    }
                });
    }

    public static void main(String[] args) {
        Core core = new Core();
        AtomicInteger interceptions = new AtomicInteger();
        Service observed = proxy(core, interceptions);

        System.out.println("direct:");
        System.out.println("result=" + core.process(2));

        System.out.println("through proxy:");
        System.out.println("result=" + observed.process(3));

        System.out.println("separate proxy step:");
        observed.internalStep();

        System.out.println("interceptions=" + interceptions.get());
        System.out.println("core processes=" + core.processCalls);
        System.out.println("core steps=" + core.stepCalls);
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac --release 17 CoverageBoundaryDemo.java
java CoverageBoundaryDemo
~~~

Stdout chính xác:

~~~text
direct:
core: process 2
core: step
result=4
through proxy:
proxy: before process
core: process 3
core: step
proxy: exit process
result=6
separate proxy step:
proxy: before internalStep
core: step
proxy: exit internalStep
interceptions=2
core processes=2
core steps=3
~~~

### 14.1. Phân tích coverage

- **core.process(2)** gọi target trực tiếp: method body chạy, nhưng interceptor không thấy lời gọi.
- **observed.process(3)** đi qua proxy: handler ghi **before process** rồi target chạy.
- Trong Core.process, lời gọi **internalStep()** vẫn chạy như một method Java bình thường và được tính vào **stepCalls**, nhưng không quay lại proxy để tạo thêm một sự kiện interceptor.
- **observed.internalStep()** gọi riêng qua proxy, nên có **before internalStep** và **exit internalStep**.
- **interceptions=2** nhưng **core steps=3**: đếm method body và đếm interception không giống nhau.

**Ý nghĩa so sánh:** một bytecode weaver instrument trực tiếp execution của internalStep có thể quan sát những lượt self-call này nếu đúng class/method được weave; proxy trong ví dụ không làm như vậy. Không được kết luận bytecode weaving luôn bao phủ mọi method: nó cũng phụ thuộc pointcut, scope và join point model.

### 14.2. Ví dụ không đo hiệu năng

System.out.println là I/O có chi phí lớn và không ổn định. AtomicInteger cũng có synchronization semantics riêng. Vì vậy không được đo tổng thời gian chạy chương trình này rồi tuyên bố overhead proxy bằng một tỷ lệ cố định.

### 14.3. Vì sao unwrap InvocationTargetException?

Khi Method.invoke gọi target và target ném ngoại lệ, Java reflection có thể bọc lỗi trong **InvocationTargetException**. Handler lấy **getCause()** để tiếp tục truyền lỗi gốc. Đây là một phần **chi phí đúng đắn** của interception: một cơ chế chỉ thêm tracing cũng có thể vô ý đổi exception nếu wrapper xử lý sai.

## 15. Tình huống 1: policy bắt buộc tại mọi đường thực thi một method

Giả sử một hệ thống có nhiều caller; một số caller giữ reference đến target gốc. Yêu cầu là “mọi execution của một method quan trọng phải được ghi nhận”.

**Phương án proxy:** có thể chưa đủ vì một số caller bypass. Có thể giải quyết bằng cách sửa kiến trúc để mọi caller chỉ được cấp proxy và không truy cập trực tiếp target, nhưng đó là một điều kiện cần bảo đảm bằng code review và integration test.

**Phương án execution weaving:** có thể phù hợp hơn nếu instrument được chính method thực thi, kể cả subclass override quan trọng và class loader liên quan. Tuy nhiên vẫn phải xác minh vùng weave, dynamic pointcut, lỗi sau refactor và việc advice có thể throw.

Đánh đổi: coverage mạnh hơn trong phạm vi method đã weave có thể đi kèm **toolchain, class loading và vận hành phức tạp hơn**. Không nên chọn weaving sâu nếu một boundary proxy được kiểm soát chặt đã đáp ứng đầy đủ yêu cầu.

## 16. Tình huống 2: thư viện chỉ có binary, không kiểm soát source

Đầu vào có thể là JAR của một thư viện.

- **Source-level weave:** không có source để transform theo pipeline thông thường.
- **Post-compile binary weave:** có thể áp dụng nếu engine hiểu class version, phạm vi pháp lý/kỹ thuật cho phép và output vẫn hợp lệ.
- **Load-time weave:** có thể instrument class khi runtime load, nhưng cần agent, loader, module và tính tương thích.
- **Proxy:** có thể bọc API công khai nếu caller sử dụng proxy, nhưng không quan sát mọi method/field nội bộ.

Câu hỏi quyết định không chỉ là “có binary không”, mà còn là **join point muốn quan sát nằm ở API hay sâu bên trong implementation**, và có quản lý được runtime/classloader không.

## 17. Tình huống 3: yêu cầu khởi động nhanh và deploy thường xuyên

Một hệ thống nhiều instance được tạo/hủy thường xuyên có thể nhạy cảm với startup:

- CTW/PCW đã trả phần lớn chi phí transform tại build/release.
- LTW có thể thêm chi phí khi class nạp/define, đáng chú ý ở cold-start.
- Proxy có thể trả chi phí tạo chain khi dựng object graph và thêm dispatch mỗi call.
- Advice I/O vẫn có thể chiếm phần lớn trong tất cả chiến lược.

Tuy nhiên không được kết luận “LTW luôn startup chậm hơn” nếu chưa đo: số class được instrument, agent, lazy loading, JIT, class sharing và tool implementation đều có ảnh hưởng.

Một quyết định có cơ sở cần ít nhất **cold-start p95, tổng thời gian boot, CPU/memory peak**, bên cạnh steady-state latency. Nếu build dài ra nhưng deploy nhanh hơn, team phải cân nhắc thời gian CI/CD và yêu cầu availability.

## 18. Tình huống 4: muốn bật/tắt hoặc đổi concern mà không build lại

Runtime interceptor chain thường thuận tiện cho cấu hình linh hoạt **nếu** kiến trúc có cách cấp lại proxy hoặc thay handler trong phạm vi hợp lệ. Nhưng không phải mọi proxy hiện tại tự cập nhật theo config mới.

LTW có thể nhận config mới cho các class **được define sau**, trong khi class đã define có thể cần restart hoặc retransform/redefine được hỗ trợ. CTW/PCW thường cần artifact mới khi aspect đã được nhúng vào binary.

Nếu yêu cầu đổi policy nhanh, hãy viết rõ:

- Những class/objects đang sống có cần cập nhật không?
- Có chấp nhận restart không?
- Thời gian rollout và rollback mong muốn là gì?
- Có cần consistency giữa các instance tại cùng thời điểm không?
- Làm sao biết chính xác version policy đang áp dụng cho một invocation?

Một giải pháp “dynamic” nhưng thiếu quan sát version runtime có thể khó kiểm soát hơn deploy một artifact bất biến.

## 19. Tình huống 5: nhiều class loader và extension/plugin

Trong JVM, class identity gắn với **binary name** và **defining class loader**. Một class tên giống nhau có thể được định nghĩa riêng ở hai loader khác nhau.

- Compile-time/post-compile cần biết **artifact nào** chứa class thực sự sẽ được runtime dùng.
- LTW phải có transformer áp dụng trên **loader** liên quan, có dependency và visibility phù hợp.
- Proxy phải được tạo cho **interface/Class có identity tương thích** với caller và target.
- Aspect helper cần hiện diện trong đúng loading context để không gây LinkageError hoặc class cast ngoài ý định.

Khi module/plugin sinh code và load động, phải kiểm tra đúng đường, không chỉ tên class trong log. “Class A đã được weave” không tự nghĩa tất cả class có cùng tên trong mọi loader đều đã được weave.

## 20. Rủi ro chồng nhiều cơ chế

Một ứng dụng có thể vừa có proxy tại service boundary vừa có một bytecode weaver instrument execution:

~~~text
Caller
   └─► Proxy trace
           └─► Woven target execution
                   └─► Business core
~~~

Kết quả có thể là **hai event** cho một invocation nghiệp vụ. Nếu proxy retry, woven execution có thể chạy nhiều lần trong khi proxy chỉ tạo một event ngoài retry.

Để tránh đo sai:

1. Chỉ định **owner** cho từng concern và biên đo.
2. Ghi **join point kind, signature, correlation ID** trong test.
3. Kiểm tra thứ tự advice giữa các tầng.
4. Phân biệt số lần target chạy với số lần interceptor được gọi.
5. Không dùng cùng nhãn metric “request completed” cho cả biên call và execution khi chúng có thể lồng nhau.
6. Đảm bảo quanh thao tác có side effect, retry phải an toàn/idempotent.

Kết hợp nhiều chiến lược không nhất thiết sai, nhưng làm tăng chi phí cấu hình, gỡ lỗi và hiểu semantics của chương trình.

## 21. Bảng so sánh mức độ phức tạp vận hành theo tác vụ

| Tác vụ vận hành | Compile-time | Post-compile | Load-time | Proxy |
|---|---|---|---|---|
| Thay aspect | Rebuild | Reweave + redeploy | Đổi config/agent, xem lifecycle class | Đổi chain/reference, xem lifecycle object |
| Đối chiếu đầu ra | Source/compiled artifact | Binary woven | Bytes/class runtime, diagnostics | Object graph/handler order |
| Debug không match | Compiler/pointcut diagnostics | Binary match report | Loader/transform logs | Routing và dynamic match |
| Xử lý version JVM mới | Compiler/plugin compatibility | Bytecode parser/verification | Agent/transformer compatibility | Proxy API/handler compatibility |
| Rollback | Bản build cũ | Woven artifact cũ | Config/agent/restart hợp lệ | Wiring/handler version cũ |
| Class mới sinh runtime | Ngoài build có thể bỏ sót | Ngoài release có thể bỏ sót | Có thể instrument khi define | Có thể bọc khi object được tạo |
| Chặn self-invocation | Phụ thuộc join point đã dệt | Phụ thuộc execution woven | Phụ thuộc execution woven | Thường bypass |
| Kiểm soát đường trực tiếp | Body được weave có thể vẫn chặn | Body woven có thể vẫn chặn | Body woven có thể vẫn chặn | Cần ngăn bypass |

Các cụm “có thể” trong bảng là điều kiện cố ý: **khả năng phụ thuộc công cụ và cấu hình**, không chỉ thời điểm.

## 22. Kiểm thử coverage theo ma trận thay vì một happy path

Tạo fixture:

~~~text
Interface Operation
       ▲
       │
BaseOperation
       ▲
       ├── InheritingOperation  (không override)
       └── OverridingOperation (override)

Caller A qua interface
Caller B qua target gốc
Target gọi method nội bộ
Một class từ loader khác nếu kiến trúc có
~~~

Các test cần hỏi:

| Tình huống | Điều bắt buộc kiểm tra |
|---|---|
| Caller qua proxy | Advice có chạy đúng một lần tại boundary? |
| Caller trực tiếp target | Có bypass proxy không, policy có chấp nhận không? |
| Target self-call | Có execution advice khi được weave, hay không có proxy event? |
| Override ở subclass | Execution thực nằm đâu, class subclass có được weave? |
| Method kế thừa | Thân khai báo ở superclass có được instrument? |
| Hai caller khác nhau | Call pointcut đã bao đủ những caller cần thiết? |
| Static/private/final | Join point model và interception hỗ trợ ra sao? |
| Target ném exception | Advice thứ tự/exception contract có đúng? |
| Before/after advice ném exception | Có vô ý chặn/che lỗi nghiệp vụ? |
| Retry/nested method | Số lần target và advice có chính xác? |
| Dynamic condition false | Không chạy advice ở ca bị loại? |
| Nhiều class loader | Đúng định nghĩa runtime được bao phủ? |
| Aspect/config đổi | Output cũ/mới có được áp dụng nhất quán? |

Những test “không được chạy” giúp phát hiện pointcut quá rộng; test “phải chạy” giúp phát hiện thiếu đường. Chỉ xem log ở một happy path không chứng minh coverage.

## 23. Quy trình ra quyết định có thể lặp lại

### Bước 1 — Viết policy

Ví dụ “mỗi execution của method nhận tiền trên mọi implementation phải qua policy” hoặc “chỉ đo số request qua API boundary”. Hai yêu cầu này không tương đương.

### Bước 2 — Liệt kê join points và đường gọi

Đánh dấu call/execution, caller, receiver, override, self-call, constructor/field/static nếu liên quan. Xác định lớp nào cần được instrument và caller nào có thể bypass.

### Bước 3 — Đặt trọng số cho mục tiêu

Xếp hạng **bắt buộc** và **mong muốn**:

- Coverage correctness.
- Startup latency.
- Steady-state overhead.
- Build time và thời gian release.
- Operability/debuggability.
- Policy update/rollback speed.
- Quyền truy cập source/binary và bảo mật.

Không nên cộng điểm cơ học khi một tiêu chí **bắt buộc** không được đáp ứng. Ví dụ bảo mật cần bao phủ mọi đường nhưng proxy không được quản lý toàn bộ reference: “proxy dễ vận hành” không bù được lỗ hổng coverage.

### Bước 4 — Chọn hai phương án có khả năng đáp ứng

Loại ngay giải pháp không có join point model hoặc không kiểm soát được đường gọi. Chỉ benchmark những phương án đủ yêu cầu chức năng.

### Bước 5 — Tạo PoC thực tế

Thử một method chính, một self-call, một subclass override, một đường lỗi và một đường bypass. Với LTW, thử class nạp muộn; với PCW, kiểm chứng đúng woven artifact; với proxy, xác định caller nhận proxy.

### Bước 6 — Đo chi phí cùng workload

Tách build/startup/per invocation và advice I/O. Dùng cùng JDK và môi trường, báo throughput, latency p95/p99, allocation, memory và khả năng ổn định.

### Bước 7 — Kiểm tra sự cố và rollback

Đưa ra một kịch bản “pointcut không match sau refactor”, một kịch bản “transformer lỗi khi startup”, hoặc “proxy wiring bị bỏ qua”, rồi đánh giá thời gian chẩn đoán và phục hồi.

### Bước 8 — Chốt cùng bằng chứng

Lưu decision record gồm yêu cầu, các phương án bị loại, rủi ro còn lại, test coverage, benchmark thực và phương án rollback. Không ghi con số hiệu năng nếu chưa đo.

## 24. Các sai lầm thường gặp

**Sai lầm 1 — “Compile-time luôn ít chi phí runtime hơn”.** Advice và dynamic checks vẫn chạy mỗi lần cần thiết; chỉ có một phần chi phí transform chuyển về build.

**Sai lầm 2 — “Load-time transformer chạy ở mọi lời gọi method”.** Nó có thể chạy khi class được define, còn method chạy nhiều lần sau đó.

**Sai lầm 3 — “Proxy luôn chậm hơn bytecode một tỷ lệ cố định”.** Hiệu năng phụ thuộc implementation, JIT, số interceptor, advice body và workload; cần benchmark.

**Sai lầm 4 — “Dệt ở compile đảm bảo bao phủ thư viện ngoài”.** Chỉ những nguồn/artifact được đưa vào pipeline và được engine hỗ trợ mới có cơ hội weave.

**Sai lầm 5 — “Đã có proxy thì self-invocation cũng bị chặn”.** Lời gọi nội bộ trên target có thể bỏ qua proxy.

**Sai lầm 6 — “LTW bao phủ mọi class sau khi agent đăng ký”.** Cần xem loader, include/exclude, module, pointcut, định nghĩa trước đó và khả năng tương thích.

**Sai lầm 7 — “Một log before nghĩa code gốc bị biến đổi”.** Runtime proxy/decorator cũng có thể tạo log mà target binary vẫn nguyên.

**Sai lầm 8 — “Có woven binary trên đĩa nghĩa JVM đang chạy đúng nó”.** Có thể classpath hoặc loader đưa binary khác vào runtime.

**Sai lầm 9 — “Advice đếm 2 nghĩa target xử lý hai request”.** Call/execution, retry, nested method và multiple aspects có thể sinh nhiều advice events hơn số nghiệp vụ.

**Sai lầm 10 — “Chi phí chỉ là CPU per invocation”.** Build time, cold-start, memory, artifact size, debugger và incident recovery đều có tác động vận hành.

**Sai lầm 11 — “Có thể đổi aspect ở runtime mà mọi class/instance lập tức cập nhật”.** Tùy pha composition, lifecycle và khả năng hỗ trợ cập nhật.

**Sai lầm 12 — “Pointcut rộng là chắc chắn hơn”.** Nó có thể chặn nhầm helper, gây recursion, log dữ liệu nhạy cảm hoặc thay hành vi ngoài ý định.

**Sai lầm 13 — “Final/private/static đều không thể áp dụng AOP”.** Đây là kết luận quá rộng; cần phân biệt subclass proxy, interface proxy và bytecode execution weaving.

**Sai lầm 14 — “Một công cụ mạnh về join point chắc chắn dễ vận hành hơn”.** Coverage nhiều hơn có thể đi cùng độ khó debugging, startup và compatibility cao hơn.

## 25. Tự kiểm tra và trả lời

**Câu 1.** Một class đã được weave lúc build nhưng method chưa chạy. Có advice invocation chưa?

**Đáp:** Chưa chỉ vì weaving đã hoàn tất. Advice chạy khi join point phù hợp thật sự xuất hiện.

**Câu 2.** Nếu một yêu cầu bảo mật phải áp dụng cho mọi execution của method nhưng caller có thể gọi trực tiếp target, proxy có đáp ứng mặc nhiên không?

**Đáp:** Không. Cần kiểm soát mọi đường reference hoặc dùng cơ chế khác có coverage đã được kiểm chứng.

**Câu 3.** Vì sao load-time weaving có thể làm startup nặng hơn nhưng không nhất thiết làm transform lặp lại trên mỗi invocation?

**Đáp:** Transformer làm việc khi class được định nghĩa; code đã instrument sau đó chạy như class được JVM định nghĩa.

**Câu 4.** Tại sao post-compile weaving cần quản trị provenance chặt?

**Đáp:** Phải chắc chắn runtime dùng đúng woven binary và có thể tái tạo/rollback artifact, không nhầm với bản gốc.

**Câu 5.** Nếu bytecode weaver chặn được execution của inner, lời gọi outer tự gọi inner có thể được advice quan sát không?

**Đáp:** Có nếu class/method execution ấy thực sự được weave và pointcut khớp, khác với self-call có thể bypass proxy.

**Câu 6.** Có nên kết luận proxy chậm hơn khi demo print nhiều dòng log hơn?

**Đáp:** Không. Logging I/O làm méo phép đo; cần benchmark kiểm soát tương đương advice và warmup/JIT.

**Câu 7.** Một class có tên giống nhau được loader A và B định nghĩa. Weave ở A bảo đảm B cũng weave không?

**Đáp:** Không. Runtime class identity và transformer scope cần xét từng defining loader.

**Câu 8.** Một pointcut có điều kiện target subtype. Compile-time weaving có thể tự biết mọi object runtime sẽ thỏa không?

**Đáp:** Không nhất thiết. Engine có thể phải chèn runtime type check ở các join point ứng viên.

**Câu 9.** Khi vừa có proxy, vừa có execution advice trong class target, một request có thể tạo hai trace không?

**Đáp:** Có; cần phân biệt join point và ownership của metric để tránh đếm đôi.

**Câu 10.** Hai phương án có chức năng giống nhau, một giảm runtime overhead nhưng làm build chậm hơn. Chọn như thế nào?

**Đáp:** Dựa vào tần suất build, số lượt invocation, startup, SLO, chi phí CI/CD, benchmark thực và độ phức tạp rollback. Không có lựa chọn phổ quát.

**Câu 11.** Chỉ thấy tool báo “weaving complete” có đủ chứng minh coverage không?

**Đáp:** Không. Phải kiểm chứng artifact/class/route đã sử dụng và test cả join point phải khớp/không được khớp ở runtime.

**Câu 12.** Khi nào runtime proxy có lợi thế vận hành?

**Đáp:** Khi boundary rõ, reference được kiểm soát, không cần chặn sâu trong implementation và chain dễ cấu hình/quan sát theo vòng đời ứng dụng.

## 26. Sơ đồ ra quyết định ngắn

~~~text
          Policy cần quan sát những join point nào?
                            │
                 ┌──────────┴──────────┐
                 ▼                     ▼
       API boundary có thể        Phải chặn execution
       kiểm soát reference?       bên trong / call sites?
                 │                     │
                 ▼                     ▼
          Proxy/decorator         Source/IR/bytecode weave
          là ứng viên             là ứng viên
                 │                     │
                 └──────────┬──────────┘
                            ▼
                 Có source/binary và
                 kiểm soát build không?
                      ┌─────┴──────┐
                      ▼            ▼
                     Có           Không/khó
                      │            │
                      ▼            ▼
              Compile/post-     Xem load-time
              compile weave     nếu engine hỗ trợ
                      │            │
                      └─────┬──────┘
                            ▼
                 Test coverage bắt buộc
                 và trường hợp không match
                            │
                            ▼
                 Đo build/startup/runtime
                 + chi phí vận hành/rollback
                            │
                            ▼
                  Chọn theo yêu cầu thật
~~~

**Kết luận:** không có một thời điểm dệt AOP nào đồng thời tối ưu mọi trục. Compile-time/post-compile thường giúp đóng gói kết quả vào artifact trước deploy; load-time tạo khả năng instrument khi class được nạp nhưng làm tăng độ khó quản lý agent/classloader; proxy thuận tiện cho boundary rõ nhưng phụ thuộc đường gọi. Việc chọn đúng đòi hỏi **ma trận coverage có thể kiểm chứng**, **phân bổ chi phí theo pha**, **quy trình debugging/rollback** và benchmark trên hệ thống thực.

## Tài liệu tham khảo

- [Java Virtual Machine Specification, Java SE 17 – The Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): cấu trúc class file và ràng buộc bytecode verification.
- [Java Virtual Machine Specification, Java SE 17 – Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): vòng đời class, class loading và initialization.
- [Java SE 17 – Instrumentation API](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): transformer, retransform/redefine cùng những giới hạn runtime.
- [Java SE 17 – InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): JDK dynamic proxy dùng trong ví dụ Java runnable.
- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): mô hình join point, pointcut, advice và các chiến lược weaving trong một ngôn ngữ AOP cụ thể.
