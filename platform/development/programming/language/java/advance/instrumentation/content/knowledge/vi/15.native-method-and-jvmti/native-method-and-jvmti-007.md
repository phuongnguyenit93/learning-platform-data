# JVM TI: capabilities, giai đoạn hoạt động và ClassFileLoadHook ở mức tổng quan

Java Virtual Machine Tool Interface (**JVM TI**, thường viết `JVMTI`) là giao diện native do JVM cung cấp cho các công cụ như debugger, profiler, tracing agent và bytecode instrumentation. Khi muốn quan sát JVM ở mức thấp hơn `java.lang.instrument`, một native agent có thể đăng ký callback lúc JVM nhận class-file bytes, trước khi xây biểu diễn class nội bộ, hoặc dùng API để đọc thread, stack, heap và trạng thái runtime — **nếu tính năng ấy được JVM hỗ trợ, agent có capability phù hợp và đang ở đúng giai đoạn hoạt động**.

Ba khái niệm phải luôn được xét cùng nhau:

1. **Capability:** môi trường JVM TI (`jvmtiEnv*`) có được phép sử dụng tính năng tùy chọn hay không, ví dụ `can_retransform_classes`.
2. **Phase:** JVM đã khởi động tới giai đoạn nào; một số JVMTI functions/callbacks không hợp lệ khi VM còn quá sớm hoặc đã kết thúc.
3. **Event callback:** native agent đăng ký hàm nhận sự kiện rồi bật notification; `ClassFileLoadHook` cho phép xem hoặc thay classfile bytes trên đường JVM tải, redefine hoặc retransform lớp.

Bài này thuộc nhóm **Native và JVM TI**. Trọng tâm là bức tranh tổng quan, đúng ranh giới của API, cách debug khi thiếu event, và ví dụ Java 17+ đi cùng một native agent C nhỏ theo chế độ **chỉ quan sát, không sửa bytecode**. Nó không giả định bạn phải viết một bytecode rewriter phức tạp trước khi hiểu vòng đời JVM.

## 1. JVM TI nằm ở đâu trong hệ sinh thái Java?

~~~text
Java application                       Native profiling / debugging tool
  |                                               |
  |           Java instrumentation agent          |
  |           premain/agentmain                    |
  |           Instrumentation                      |
  v                    |                          v
ClassLoader ---> Java ClassFileTransformer     JVM TI native agent
  |                                              Agent_OnLoad
  |                                              jvmtiEnv*
  |                                              ClassFileLoadHook
  +--------------------+---------------------------+
                       |
                       v
                       JVM
           class loading / verification
           linking / execution / GC / threads
~~~

Các khái niệm dễ nhầm:

| API hoặc thành phần | Ngôn ngữ / điểm vào | Mục đích chính |
| --- | --- | --- |
| **JNI** | C/C++ kết nối với Java code và objects | Gọi native từ Java hoặc gọi Java qua `JNIEnv*`, quản lý JNI references |
| **JVM TI** | C/C++ agent với `Agent_OnLoad`, `jvmtiEnv*` | Tương tác với JVM cho tooling: events, capabilities, threads, classes, bytecode |
| **Java Instrumentation** | Java agent có `premain`/`agentmain`, `Instrumentation` | Đăng ký `ClassFileTransformer`, redefine/retransform classes từ Java |
| **JFR / JMX / logging** | API quan sát ở mức cao hơn | Ghi nhận và xuất dữ liệu vận hành mà không nhất thiết thao tác trực tiếp với classfile bytes |

JNI và JVM TI thường xuất hiện cùng một native agent, nhưng **chúng không thay thế nhau**. `JNIEnv*` phục vụ tương tác JNI với Java world; `jvmtiEnv*` cung cấp các JVMTI functions và state riêng của môi trường tooling. JVM TI không phải một thư viện Java thuần chỉ cần thêm dependency Maven; nó là giao diện native do một JVM implementation hỗ trợ.

Một JVMTI agent điển hình là dynamic library `.so` (Linux), `.dylib` (macOS) hoặc `.dll` (Windows). JVM nạp thư viện qua `-agentpath:/absolute/path/to/library` hoặc `-agentlib:name` nếu loader path đã được cấu hình. **`-javaagent` là cơ chế cho Java instrumentation JAR**, không phải lệnh tương đương để nạp file C `.dll`.

### 1.1. Thuật ngữ “môi trường” là gì?

JVM có thể tạo một hoặc nhiều `jvmtiEnv*` trong cùng tiến trình cho những native agents, mỗi environment có capability set, callback table và notification state của mình. Vì vậy đừng suy rằng capability được agent A cấp sẽ tự xuất hiện trong mọi environment khác; cũng không nên dựa vào một global callback duy nhất cho cả JVM.

Trong C, `jvmtiEnv*` được lấy từ `JavaVM*` qua `GetEnv` với phiên bản JVMTI được yêu cầu. Mỗi lệnh JVMTI trả về `jvmtiError`; khác với lời gọi Java vốn có thể ném exception. **Luôn kiểm tra mã lỗi** trong phần setup thay vì giả định hàm trả về thành công.

## 2. Vòng đời JVM TI: năm giai đoạn hoạt động

JVM TI quy định enum `jvmtiPhase`. Thứ tự thời gian là:

~~~text
Agent_OnLoad
   |
   v
ONLOAD ---------------------- chuẩn bị agent, hỏi/cấp capabilities
   |
   v
PRIMORDIAL ------------------ VM đang bootstrap, JNI chưa luôn sẵn sàng
   |
   v
START ------ VMStart -------- một phần VM/Java runtime đã sẵn sàng
   |
   v
LIVE ------- VMInit --------- ứng dụng chạy, phần lớn tooling APIs hoạt động
   |
   v
DEAD ------- VMDeath -------- VM đóng hoặc startup thất bại
~~~

| Phase | Hằng `jvmtiPhase` | Ngữ nghĩa |
| --- | --- | --- |
| OnLoad | `JVMTI_PHASE_ONLOAD` | Trong `Agent_OnLoad`; thường là thời điểm thích hợp để thương lượng optional capabilities và đăng ký callback |
| Primordial | `JVMTI_PHASE_PRIMORDIAL` | Sau `Agent_OnLoad`, trước `VMStart`; VM còn ở giai đoạn cực sớm |
| Start | `JVMTI_PHASE_START` | Sau `VMStart` tới `VMInit`; một số hàm JNI và JVMTI đã cho phép |
| Live | `JVMTI_PHASE_LIVE` | Từ `VMInit` đến khi `VMDeath` kết thúc; phần lớn JVMTI operations hợp lệ |
| Dead | `JVMTI_PHASE_DEAD` | Sau `VMDeath` hoặc startup thất bại; không còn runtime Java bình thường |

**Không so sánh trực tiếp giá trị số enum để suy thứ tự pha.** Theo đặc tả, ví dụ `JVMTI_PHASE_START` có giá trị số 6 còn `JVMTI_PHASE_LIVE` có giá trị 4; đó là mã enum, không phải số bước tăng dần. Khi cần biết phase thật, gọi:

~~~c
jvmtiPhase phase;
jvmtiError err = (*jvmti)->GetPhase(jvmti, &phase);
~~~

Đoạn này chỉ là **snippet native**, giả định `jvmti` là environment hợp lệ. `GetPhase` là API được phép gọi trong bất kỳ phase nào, nhưng **không vì thế mọi function khác cũng hợp lệ ở bất kỳ phase**.

### 2.1. Tại sao phase là một ràng buộc thực?

Một số JVMTI APIs chỉ cho gọi ở **Live**; một số dùng ở OnLoad hoặc Live; một số như `GetPhase` có thể gọi trong nhiều giai đoạn. Nếu gọi sai, JVM TI có thể trả mã `JVMTI_ERROR_WRONG_PHASE`. Ví dụ bạn không nên viết callback chạy trong pha Primordial rồi dùng hàng loạt JNI reflective calls như thể Java runtime đã init xong.

Tài liệu cũng nói JNI functions thông thường chỉ dùng trong **Start/Live**; vì vậy **`JNIEnv*` trong `ClassFileLoadHook` có thể là `NULL` nếu hook xảy ra ở Primordial**. Đừng dereference hoặc dùng `jni_env` khi chưa chắc phase và pointer. Nhiều lỗi agent startup rất khó debug chỉ vì gọi sớm `FindClass` hoặc chạm vào logger Java trong hook.

**Phân biệt hai mốc:** `VMStart` đánh dấu chuyển vào Start, còn `VMInit` đánh dấu chuyển vào Live. Đừng viết "mọi thứ đều Live từ VMStart"; đó là cách giải thích không chính xác.

### 2.2. Agent startup và attach vào JVM đã chạy

| Cơ chế | Điểm vào native | Thời điểm |
| --- | --- | --- |
| `-agentpath:/path/libobserve.so` lúc launcher startup | `Agent_OnLoad(JavaVM*, char*, void*)` | OnLoad, trước phần lớn ứng dụng Java |
| `-agentlib:observe` lúc launcher startup | `Agent_OnLoad(...)` | Tương tự, JVM tìm library theo search path |
| Native agent được attach vào JVM đang chạy (nếu hỗ trợ) | `Agent_OnAttach(...)` | Thường ở Live; một số capabilities OnLoad-only có thể không còn thêm được |
| JVM shutdown | Có thể gọi `Agent_OnUnload(JavaVM*)` | Dọn resource native theo contract; không gọi lại API tùy tiện khi JVM đã chết |

Vì **capability khả dụng còn phụ thuộc phase**, agent cần hook rất sớm có lý do để được nạp khi JVM startup. Attach muộn vẫn hữu ích cho diagnostics, nhưng không tự lấy lại những `ClassFileLoadHook` đã trôi qua ở giai đoạn nạp class trước đó.

## 3. Capabilities: ba câu hỏi khi dùng tính năng tùy chọn

Không phải mọi JVMTI implementation đều hỗ trợ mọi feature. Một số thao tác cần capability riêng, ví dụ `can_retransform_classes` để dùng `RetransformClasses` hoặc `can_generate_method_entry_events` để phát event method entry.

Hãy tách ba phép kiểm:

| Câu hỏi | JVM TI function | Ý nghĩa |
| --- | --- | --- |
| Môi trường **có thể xin** capability nào ở phase hiện tại? | `GetPotentialCapabilities` | Danh sách khả năng **có thể đạt được lúc này**, có thể phụ thuộc JVM/phase và agents khác |
| Agent muốn **được cấp** capability nào? | `AddCapabilities` | Bổ sung những bits được set trong `jvmtiCapabilities` |
| Environment **đang sở hữu** capability nào? | `GetCapabilities` | Giá trị thực sự đã được grant; không đồng nghĩa mọi potential capabilities đều sở hữu |

Hình dung:

~~~text
GetPotentialCapabilities()
       |
       v
"JVM có thể cấp gì NGAY BÂY GIỜ?"
       |
       v
Chọn những bits thật sự cần
       |
       v
AddCapabilities(request)
       |
       +-- JVMTI_ERROR_NONE -> đã được cấp theo yêu cầu
       |
       +-- error           -> không giả định có quyền
       |
       v
GetCapabilities() -> xác nhận capabilities đang sở hữu
       |
       v
SetEventCallbacks(...) và SetEventNotificationMode(...)
~~~

`AddCapabilities` là phép **bổ sung**, không phải đặt lại toàn bộ capability set. Một số capabilities có thể chỉ xin được trong `OnLoad`; nếu đến Live mới xin, `GetPotentialCapabilities` có thể không còn liệt kê chúng. Các quyền có thể bị giới hạn bởi JVM vendor, startup flags hoặc một JVMTI environment khác đang giữ capability độc quyền.

**Không nên dùng `AddCapabilities` với toàn bộ bitmask potential chỉ để “cho chắc”.** Xin quyền không cần thiết có thể tăng overhead hoặc thay đổi khả năng tối ưu hóa của VM; một số capabilities chiếm tài nguyên/khóa cơ chế JVM đặc biệt. Yêu cầu đúng những gì agent thực sự dùng và có cách fallback khi JVM không cung cấp.

### 3.1. Ví dụ cấu hình capability có kiểm tra

Trong C, sau khi đã lấy được `jvmtiEnv*`:

~~~c
jvmtiCapabilities potential;
jvmtiCapabilities wanted;
jvmtiCapabilities owned;

memset(&potential, 0, sizeof(potential));
memset(&wanted, 0, sizeof(wanted));
memset(&owned, 0, sizeof(owned));

jvmtiError err = (*jvmti)->GetPotentialCapabilities(jvmti, &potential);
if (err != JVMTI_ERROR_NONE) {
    return JNI_ERR;
}
if (potential.can_generate_all_class_hook_events) {
    wanted.can_generate_all_class_hook_events = 1;
    err = (*jvmti)->AddCapabilities(jvmti, &wanted);
    if (err != JVMTI_ERROR_NONE) {
        return JNI_ERR;
    }
}
err = (*jvmti)->GetCapabilities(jvmti, &owned);
if (err != JVMTI_ERROR_NONE) {
    return JNI_ERR;
}
~~~

Đây là **mảnh native code**, không phải chương trình độc lập. `jvmti` phải là environment hợp lệ, `string.h` đã được include và `return JNI_ERR` nằm trong hàm trả về `jint` như `Agent_OnLoad`. `can_generate_all_class_hook_events` là optional feature để có `ClassFileLoadHook` cho toàn bộ nhóm classes được đặc tả; nếu không available, agent phải chấp nhận coverage thấp hơn, không giả mạo trạng thái “đã có quyền”.

Trong ví dụ thực thi ở mục 7, ta sẽ dùng phần xin capability có kiểm tra này nhưng **không yêu cầu early hooks hoặc retransformation**, vì mục tiêu chỉ là quan sát một lớp ứng dụng được nạp bình thường.

### 3.2. Capability liên quan trực tiếp tới `ClassFileLoadHook`

| Capability | Mục đích | Quy tắc cần nhớ |
| --- | --- | --- |
| `can_generate_all_class_hook_events` | Cho phép nhận ClassFileLoadHook cho mọi lớp thuộc phạm vi đặc tả mà JVM hỗ trợ | Một số loại class đặc biệt có thể không gửi hook theo JVM implementation |
| `can_generate_early_class_hook_events` | Cho phép hook trong pha **Primordial** | Muốn early hook, cần **cả** `can_generate_early_class_hook_events` và `can_generate_all_class_hook_events` |
| `can_retransform_classes` | Cho phép gọi `RetransformClasses` và có môi trường retransform-capable | **Phải cấp trước khi `ClassFileLoadHook` được enable lần đầu** cho environment đó |
| `can_redefine_classes` | Cho phép dùng `RedefineClasses` | Cần kiểm tra cả giới hạn của từng class và VM |
| `can_generate_method_entry_events` | Nhận method entry events | Không phải yêu cầu bắt buộc để chỉ quan sát ClassFileLoadHook |

**Đây không phải bảng capability bắt buộc cho mọi hook:** `ClassFileLoadHook` bản thân là event cơ bản của JVM TI, và các capabilities trên bật **khả năng mở rộng** hoặc thao tác khác. Không khẳng định cứ thiếu `can_generate_all_class_hook_events` thì hoàn toàn không nhận được hook cho một lớp ứng dụng thông thường.

Một cạm bẫy lớn:

~~~text
Sai thứ tự khi cần retransform-capable:
    SetEventNotificationMode(ENABLE, CLASS_FILE_LOAD_HOOK)
    AddCapabilities(can_retransform_classes)   <-- quá muộn để đổi loại env

Thứ tự đúng:
    GetPotentialCapabilities
    AddCapabilities(can_retransform_classes)  <-- trước lần enable đầu
    SetEventCallbacks
    SetEventNotificationMode(ENABLE, CLASS_FILE_LOAD_HOOK)
~~~

Tài liệu xác định **loại môi trường retransformation-capable/incapable tại lúc `ClassFileLoadHook` được enable lần đầu**. Thêm một bit capability muộn không phải cách hợp lệ để biến môi trường đã xếp loại non-capable thành capable cho callback. Nếu ngay từ đầu cần retransform, cấu hình capability trước khi bật event.

## 4. Event callbacks: đăng ký hàm chưa đủ, còn phải bật thông báo

Một JVMTI environment có thể đăng ký một bảng callback, gồm từng function pointer cho `VMInit`, `VMDeath`, `ClassFileLoadHook` và nhiều events khác.

Ba bước setup cơ bản:

~~~text
Agent_OnLoad
    |
    v
GetEnv -> jvmtiEnv*
    |
    v
(Thương lượng capability cần thiết)
    |
    v
SetEventCallbacks(callback table, sizeof(table))
    |
    v
SetEventNotificationMode(JVMTI_ENABLE,
                         JVMTI_EVENT_CLASS_FILE_LOAD_HOOK,
                         NULL)
    |
    v
JVM phát event -> function pointer ClassFileLoadHook
~~~

- `SetEventCallbacks` đăng ký function pointers; nó **không đồng nghĩa** event sẽ tự được bật.
- `SetEventNotificationMode` quyết định bật/tắt notification cho event. Với ClassFileLoadHook của demo dùng `NULL` cho thread argument để bật theo phạm vi event hợp lệ.
- Cả hai hàm có quy tắc phase; có thể gọi ở `OnLoad` để bắt đầu theo dõi sớm, hoặc `Live` trong điều kiện phù hợp.
- Nếu agent đăng ký/bật quá muộn, những class đã đi qua class loading **không tự phát lại hook** chỉ vì có callback mới.
- Nếu nhiều environments đăng ký hook, JVM có pipeline/chaining; mỗi callback không nhất thiết thấy chính bytes trên đĩa.

### 4.1. Event `ClassFileLoadHook` là gì?

**ClassFileLoadHook** được phát khi JVM có class-file bytes và **trước khi dựng biểu diễn class trong bộ nhớ**. Nó cũng có thể phát khi `RetransformClasses` hoặc `RedefineClasses` xử lý class. Đây là điểm thích hợp để bytecode instrumentation tool sửa bytes **trước khi VM verify/link/define phiên bản mới**.

Đừng hiểu “ClassFileLoadHook” như một event chỉ xuất hiện khi classload thành công. Event cho phép can thiệp trong tiến trình định nghĩa; nếu file class không hợp lệ hoặc một transformer trả bytes lỗi, JVM có thể không cài đặt class definition cuối cùng.

Khi chỉ cần biết class đã đi qua bước chuẩn bị/định nghĩa nào, có thể quan sát thêm `ClassLoad`/`ClassPrepare` hoặc các nguồn quan sát khác theo mục tiêu. **`ClassFileLoadHook`, `ClassLoad`, `ClassPrepare` không phải cùng một mốc:**

| Event | Thời điểm/ý nghĩa | Có những thông tin nào? |
| --- | --- | --- |
| `ClassFileLoadHook` | JVM có raw class bytes trước khi dựng class (cũng dùng cho redefine/retransform) | `name`, `loader`, `class_data`, output buffer |
| `ClassLoad` | Một class đã được load; bước này còn rất sớm | `jclass` có thể chưa có đầy đủ metadata methods/fields |
| `ClassPrepare` | Class đã qua bước preparation | Thông tin methods/fields và interfaces đã sẵn sàng hơn; class chưa cần được initialize |
| `VMInit` | JVM đi vào Live | Không phải event "đã load xong mọi application classes" |

Nếu cần phân tích method signatures, không nên coi `ClassFileLoadHook` cung cấp ngay một `jclass` đã định nghĩa trong **lượt load mới**. `class_being_redefined` thường `NULL` khi load, còn field methods chưa có như đối tượng đã chuẩn bị.

## 5. Chữ ký `ClassFileLoadHook` và cách đọc dữ liệu

Theo JVM TI specification:

~~~c
void JNICALL ClassFileLoadHook(
    jvmtiEnv* jvmti_env,
    JNIEnv* jni_env,
    jclass class_being_redefined,
    jobject loader,
    const char* name,
    jobject protection_domain,
    jint class_data_len,
    const unsigned char* class_data,
    jint* new_class_data_len,
    unsigned char** new_class_data);
~~~

Ý nghĩa các tham số:

| Tham số | Ý nghĩa | Lưu ý an toàn |
| --- | --- | --- |
| `jvmti_env` | Môi trường native tooling đang nhận hook | Có capability/event state riêng, phải hợp lệ |
| `jni_env` | JNI environment của thread hiện tại | **Có thể NULL ở primordial**; không gọi JNI khi chưa được phép |
| `class_being_redefined` | `jclass` khi đang redefine hoặc retransform; null khi load mới | Không có nghĩa mọi hook đã có một `Class<?>` hoàn chỉnh |
| `loader` | Đối tượng defining class loader | Null cho bootstrap loader; không giữ strong refs vô hạn |
| `name` | Internal class name như `demo/Target` | Chuỗi **modified UTF-8**, có thể `NULL` |
| `protection_domain` | ProtectionDomain liên quan lớp | Không tự serialize toàn object ở hot path |
| `class_data_len` | Số byte của input classfile | Không phải số methods hay version |
| `class_data` | Pointer tới classfile bytes hiện tại trong pipeline | Chỉ dùng đúng vòng đời callback; không sửa input trực tiếp |
| `new_class_data_len` | Pointer nhận kích thước output mới | Chỉ đặt khi có bytecode mới hợp lệ |
| `new_class_data` | Pointer nhận buffer classfile mới | Buffer phải lấy từ `jvmtiEnv::Allocate` |

**Quan trọng về ownership:** Nếu chỉ quan sát, agent **không gán `new_class_data`** và **không cần cấp phát buffer output**. Nếu sửa classfile bytes, phải cấp phát buffer qua `(*jvmti)->Allocate(...)`; JVM chịu trách nhiệm giải phóng output ấy bằng `Deallocate`. Không trả pointer vào stack, mảng tĩnh, buffer của `malloc` hoặc chính `class_data`; không `free` output sau khi JVM đã nhận quyền sở hữu.

Nếu nhiều agents cùng nhận hook và agent A trả bytes mới, agent B ở tầng sau có thể nhận **bytes đã qua A**, chứ không bắt buộc là file gốc. Vì vậy một callback phải coi `class_data` như **input tại điểm pipeline hiện tại**, không như một bản sao luôn nguyên vẹn của `.class` được đọc từ JAR.

### 5.1. Vì sao `name` có thể NULL?

Khi JVM định nghĩa lớp mà không có tên đã chỉ định theo kiểu thường gặp, tham số `name` có thể không có sẵn. Nếu callback viết:

~~~c
// NGUY HIỂM: không kiểm tra con trỏ.
if (strcmp(name, "demo/Target") == 0) {
    /* ... */
}
~~~

thì `strcmp(NULL,...)` là undefined behavior, có thể crash **toàn tiến trình JVM**. Dùng:

~~~c
if (name != NULL && strcmp(name, "demo/Target") == 0) {
    /* xử lý event cho lớp đích */
}
~~~

Tên internal dùng dấu `/`, khác `demo.Target` của source Java. Đừng cố gọi JNI `FindClass` trong hook để dựng tên cho class đang được định nghĩa: ở một số phase `JNIEnv` chưa hợp lệ, và ngay cả trong Live, thao tác ấy có thể kích hoạt class loading lồng nhau.

### 5.2. Có được dùng `class_data` sau callback không?

Không nên giữ con trỏ `class_data` để một thread native xử lý sau. Dữ liệu đó thuộc VM và vòng đời của nó gắn với lời gọi hook hiện tại. Nếu cần phân tích bất đồng bộ, phải **copy** một phần cần thiết vào buffer do agent quản lý, kiểm soát tổng memory/retention, và ghi rõ quyền sở hữu. Lưu cả class bytes của hàng chục nghìn lớp có thể tiêu tốn hàng GB và làm lộ constants/strings nhạy cảm.

Đối với chẩn đoán tổng quan, thường chỉ cần **tên lớp, loại sự kiện, một counter và kích thước bytes**, không cần sao chép toàn bộ class data. Nếu phải sửa bytes, dùng một parser/bytecode toolkit đã kiểm tra classfile version, constant pool, frames và exception tables.

## 6. JVM TI phases và mốc của ClassFileLoadHook

Đặc tả quy định `ClassFileLoadHook` có thể xảy ra trong **Primordial, Start hoặc Live** — nhưng **không phải mọi environment đều được nhận event primordial**.

- Nếu agent có **cả** `can_generate_early_class_hook_events` và `can_generate_all_class_hook_events`, JVM có thể gửi ClassFileLoadHook ngay trong **Primordial**.
- Nếu không có tổ hợp ấy, event có thể xuất hiện từ **Start** trước khi VM initialized hoàn toàn; sau đó nó có thể xuất hiện ở Live.
- Event không được bảo đảm cho một số lớp đặc biệt (ví dụ ROMized hoặc implementation-defined classes), tùy JVM.
- Hook có thể được phát do **redefine/retransform** khi agent/VM đã ở Live, chứ không chỉ do lần load ban đầu.

Do vậy, một native agent không thể dựa vào câu "callback luôn có JNIEnv và mọi Java service đã sẵn sàng" để tự do khởi tạo logger/class loader. Trong callback early, hãy tối thiểu hóa thao tác và dùng functions được phép ở phase tương ứng.

### 6.1. Các pha không phải “cấp bậc quyền” đơn điệu

Một function được dùng trong `OnLoad` không mặc nhiên dùng được trong `Start`; một function Live-only không dùng được trong Primordial; một function Any-phase thì có thể được gọi ở nhiều giai đoạn. Hãy tra cột **Phase** cho **chính function/event** thay vì suy theo cảm tính.

Các lỗi có thể gặp:

- `JVMTI_ERROR_WRONG_PHASE`: thao tác không hợp lệ tại phase hiện tại.
- `JVMTI_ERROR_MUST_POSSESS_CAPABILITY`: thiếu capability mà operation yêu cầu.
- `JVMTI_ERROR_NOT_AVAILABLE`: một chức năng không sẵn theo điều kiện VM.
- `JVMTI_ERROR_INVALID_EVENT_TYPE` / `JVMTI_ERROR_ILLEGAL_ARGUMENT`: event hoặc tham số cấu hình sai tùy trường hợp.

Một cách điều tra có kiểm soát là gọi `GetPhase` và `GetCapabilities` ở nơi được phép rồi ghi chúng ra **ngoài callback nóng**, đối chiếu với spec và JVM version.

## 7. Demo Java 17+ và native JVMTI agent C quan sát một lớp

Mục tiêu: khi JVM tải `demo.Target`, agent C in một dòng `JVMTI_HOOK=demo/Target`, còn ứng dụng Java in `APP=hello`. Agent **không sửa bytes** và không cần một bytecode library.

### 7.1. Cấu trúc dự án

~~~text
jvmti-demo/
  observe.c
  demo/
    Target.java
    Main.java
  out/
    ... (sinh sau khi javac)
  libobserve.so   (Linux, sau khi build)
  libobserve.dylib (macOS, sau khi build)
  observe.dll     (Windows, sau khi build)
~~~

Ba tên thư viện native là **các đầu ra thay thế theo hệ điều hành**, không phải yêu cầu sinh cả ba trên một máy. `out/` là thư mục class files, không phải folder nguồn.

### 7.2. File `demo/Target.java`

~~~java
package demo;

public final class Target {
    public static String greeting() {
        return "hello";
    }
}
~~~

### 7.3. File `demo/Main.java`

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("APP=" + Target.greeting());
    }
}
~~~

`Main` chỉ gọi `Target.greeting()` ở runtime; `demo/Target` được yêu cầu nạp trước khi phương thức có thể thực thi. Không sử dụng reflection hoặc `javaagent` để kích hoạt event trong bài. Bộ source Java đã được **biên dịch bằng `javac --release 17` và chạy với `APP=hello` trên OpenJDK 24**.

### 7.4. File `observe.c` — native JVMTI agent tối giản

~~~c
#include <jni.h>
#include <jvmti.h>
#include <stdio.h>
#include <string.h>

static void JNICALL on_class_file_load(
        jvmtiEnv* jvmti,
        JNIEnv* jni,
        jclass being_redefined,
        jobject loader,
        const char* name,
        jobject protection_domain,
        jint class_data_len,
        const unsigned char* class_data,
        jint* new_class_data_len,
        unsigned char** new_class_data) {

    (void)jvmti;
    (void)jni;
    (void)being_redefined;
    (void)loader;
    (void)protection_domain;
    (void)class_data_len;
    (void)class_data;
    (void)new_class_data_len;
    (void)new_class_data;

    if (name != NULL && strcmp(name, "demo/Target") == 0) {
        puts("JVMTI_HOOK=demo/Target");
        fflush(stdout);
    }
    /* Không đặt new_class_data: không biến đổi bytecode. */
}

JNIEXPORT jint JNICALL Agent_OnLoad(
        JavaVM* vm, char* options, void* reserved) {
    (void)options;
    (void)reserved;

    jvmtiEnv* jvmti = NULL;
    jint rc = (*vm)->GetEnv(
            vm, (void**)&jvmti, JVMTI_VERSION_1_2);
    if (rc != JNI_OK || jvmti == NULL) {
        return JNI_ERR;
    }

    jvmtiCapabilities potential;
    jvmtiCapabilities wanted;
    memset(&potential, 0, sizeof(potential));
    memset(&wanted, 0, sizeof(wanted));

    jvmtiError error = (*jvmti)->GetPotentialCapabilities(
            jvmti, &potential);
    if (error != JVMTI_ERROR_NONE) {
        return JNI_ERR;
    }

    if (potential.can_generate_all_class_hook_events) {
        wanted.can_generate_all_class_hook_events = 1;
        error = (*jvmti)->AddCapabilities(jvmti, &wanted);
        if (error != JVMTI_ERROR_NONE) {
            return JNI_ERR;
        }
    }

    jvmtiEventCallbacks callbacks;
    memset(&callbacks, 0, sizeof(callbacks));
    callbacks.ClassFileLoadHook = &on_class_file_load;

    error = (*jvmti)->SetEventCallbacks(
            jvmti, &callbacks, (jint)sizeof(callbacks));
    if (error != JVMTI_ERROR_NONE) {
        return JNI_ERR;
    }

    error = (*jvmti)->SetEventNotificationMode(
            jvmti, JVMTI_ENABLE,
            JVMTI_EVENT_CLASS_FILE_LOAD_HOOK, NULL);
    if (error != JVMTI_ERROR_NONE) {
        return JNI_ERR;
    }

    puts("JVMTI_ONLOAD=OK");
    fflush(stdout);
    return JNI_OK;
}
~~~

**Giải thích:**

1. `Agent_OnLoad` là entrypoint native JVM gọi cho thư viện nạp bằng `-agentpath` ở startup; không phải `main` của chương trình C. `JNIEXPORT` và `JNICALL` bảo đảm liên kết/ABI phù hợp với JNI headers của JDK và nền tảng.
2. `GetEnv(..., JVMTI_VERSION_1_2)` lấy environment phù hợp; nếu JVM không cung cấp được, trả `JNI_ERR` để không chạy tiếp với pointer rỗng.
3. `GetPotentialCapabilities` xem có quyền `can_generate_all_class_hook_events` để xin hay không. Demo **không xin** `can_retransform_classes` hoặc early hooks vì không gọi retransform và không cần primordial.
4. `SetEventCallbacks` đăng ký hàm `on_class_file_load`; `SetEventNotificationMode` **bật** notification sau khi callback pointer đã sẵn.
5. Callback chỉ xét `name != NULL` rồi so với internal name `demo/Target`. Nó không gọi JNI, không đọc Java object, không parse classfile và không giữ pointer bytes.
6. Các tham số hiện không dùng được đánh dấu `(void)` để tránh cảnh báo compiler. Chúng là các tham số **có thật theo spec**, không phải bỏ đi vì callback không có chúng.
7. Không gán `new_class_data` nên bytecode chạy y như input ở tầng này. Chỉ có tác dụng phụ là một dòng console do native agent in, phục vụ minh họa.
8. `puts`/`fflush` trong class-loading hook **không phải mẫu production**: I/O có chi phí, có thể dùng lock libc và gây biến dạng performance. Ở ví dụ, filter rất hẹp để tránh in cho hàng nghìn classes.

**Giới hạn thử nghiệm:** phần Java của ví dụ đã được chạy thực tế. Máy dùng để soạn bài có JDK nhưng **không có C compiler thông dụng trong PATH**, nên đoạn native C chưa được build/chạy tại đây. Signature và các lệnh JVMTI đã được đối chiếu với đặc tả chính thức; hai dòng output native bên dưới là **kết quả dự kiến khi toolchain + JVM hỗ trợ đã build/chạy thành công**, không phải nhật ký đã thực thi trên máy này.

### 7.5. Biên dịch phần Java

Từ thư mục `jvmti-demo/`:

~~~bash
javac --release 17 -d out demo/Target.java demo/Main.java
~~~

Kiểm tra không dùng agent:

~~~bash
java -cp out demo.Main
~~~

**Standard output đã chạy thực tế cho phần Java:**

~~~text
APP=hello
~~~

Các file `out/demo/Main.class` và `out/demo/Target.class` đã được javac tạo; không có JVM TI logging khi chưa bật native agent.

### 7.6. Biên dịch native trên Linux

Cần JDK headers ở `$JAVA_HOME/include` và `$JAVA_HOME/include/linux`; cần GCC hoặc compiler C tương thích:

~~~bash
gcc -std=c11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libobserve.so observe.c
~~~

Sau build, chạy với **absolute path** tới thư viện:

~~~bash
java -agentpath:"$(pwd)/libobserve.so" -cp out demo.Main
~~~

Nếu `JAVA_HOME` chưa cấu hình, xác định JDK directory thực tế trước khi biên dịch. Dùng cùng kiến trúc 64-bit của JDK đang chạy. Không giả định tên library `libobserve.so` hợp lệ trên Windows/macOS.

### 7.7. Biên dịch native trên macOS

Cần Xcode Command Line Tools/Clang và JDK headers:

~~~bash
clang -std=c11 -O2 -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -o libobserve.dylib observe.c
~~~

Chạy:

~~~bash
java -agentpath:"$(pwd)/libobserve.dylib" -cp out demo.Main
~~~

Cần đúng architecture của JVM (ví dụ arm64 hoặc x86_64). Không thể nạp một dylib chỉ dành cho CPU architecture khác vào JVM hiện tại.

### 7.8. Biên dịch native trên Windows bằng MSVC

Mở **Developer Command Prompt** của Visual Studio có MSVC và JDK headers đã cấu hình; đây là lệnh dành cho `cmd.exe`, không phải cú pháp PowerShell:

~~~bat
cl /LD /O2 /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" observe.c /link /OUT:observe.dll
~~~

Chạy với **absolute path** tới DLL. Ví dụ trong Windows PowerShell tại thư mục demo, sau khi đã build:

~~~powershell
java "-agentpath:$((Resolve-Path .\observe.dll).Path)" -cp out demo.Main
~~~

`Get-Command cl`/`where cl` cần tìm thấy MSVC compiler ở terminal đang dùng. Nếu không, mở đúng Developer Command Prompt hoặc cài toolchain; việc có JDK không đồng nghĩa máy có C compiler.

### 7.9. Kết quả dự kiến khi native agent chạy thành công

Với OpenJDK HotSpot/Zulu chạy bình thường, class `demo.Target` được load sau khi native agent đã enable hook, **standard output dự kiến**:

~~~text
JVMTI_ONLOAD=OK
JVMTI_HOOK=demo/Target
APP=hello
~~~

- `JVMTI_ONLOAD=OK`: `GetEnv`, capability negotiation và event setup đều không báo lỗi.
- `JVMTI_HOOK=demo/Target`: callback nhận event cho lớp `demo.Target` trước khi JVM dùng classfile bytes hoàn chỉnh.
- `APP=hello`: logic Java hoạt động như khi chưa có agent, vì callback không sửa classfile.

**Không cam kết output tuyệt đối của mọi JVM implementation**: một JVM có thể phát sinh thêm diagnostics khác; một số classes/platforms không được hook theo cùng phạm vi, hoặc native library có thể không load do ABI/headers sai. Bài dùng class ứng dụng thông thường để tránh phụ thuộc vào những events đặc biệt.

### 7.10. Tại sao không sửa bytes trong demo?

Mục đích hiện tại là hiểu **capability, phase và hook lifecycle**. Sửa classfile đúng đòi parser, verifier, constant pool, code attributes, stack maps, exception handlers và helper visibility. Nếu tự copy ngẫu nhiên vài byte trong `class_data` rồi trả về, JVM có thể ném `ClassFormatError`, `VerifyError`, hoặc crash do native bug.

Khi thực sự biến đổi, chỉ đặt `*new_class_data_len` và `*new_class_data` sau khi đã tạo **một classfile mới hợp lệ** trong buffer được cấp bởi `jvmti->Allocate`. JVM sở hữu việc giải phóng buffer output. Không chọn một vị trí bytes tùy tiện và viết lại magic number để “thử xem hook hoạt động”.

## 8. Retransformation và ClassFileLoadHook: hai nhóm environment

Trình tự khi nhiều native agents cùng dùng JVMTI ClassFileLoadHook có đặc điểm khác nhiều event khác:

1. **Retransformation-incapable environments** được gọi trước, theo thứ tự tạo môi trường.
2. **Retransformation-capable environments** được gọi sau, cũng theo thứ tự tạo môi trường.
3. Nếu một hook trả bytes mới, bytes đó được chuyển tiếp thành input cho hook ở tầng sau.
4. Khi `RetransformClasses`, event chỉ gửi tới **environments capable**. Sửa đổi của nhóm incapable ở lần load/redefine gần nhất vẫn được tái sử dụng theo contract; chúng không nhận callback mới.

Ví dụ logic:

~~~text
Lần LOAD:
class bytes D0
  -> native agent A (incapable): tạo output A0
  -> native agent B (capable):   tạo output B0
  -> JVM define class

Lần RETRANSFORM:
baseline từ define/redefine gần nhất
  -> JVM tái áp output A0, không gọi callback A
  -> gọi callback B capable một lần nữa
  -> JVM cài định nghĩa mới nếu hợp lệ
~~~

Đừng gắn **`can_retransform_classes`** vào môi trường sau khi đã bật ClassFileLoadHook rồi nghĩ JVM sẽ tự chuyển nó sang nhóm capable. Đặc tả xác định tính capable tại **lần đầu enable hook**. Nếu cần retransform, capability đó phải được thương lượng trước khi bật event.

**Thận trọng:** phần Java `ClassFileTransformer` cũng có cách phân loại `canRetransform`; khái niệm tương tự nhưng nó là **API Java khác**. Đừng copy nguyên thứ tự Java + native chỉ từ hai dòng đăng ký ở một thư viện: spec còn định nghĩa **các nhóm môi trường**, và một JVM có thể chứa nhiều Java/native agents. Muốn chẩn đoán thứ tự chính xác, cần ghi rõ nhóm và thời điểm đăng ký.

### 8.1. Có phải retransform luôn bắt đầu từ bytes đã instrument lần trước?

Không. Quy trình tái biến đổi khởi đầu từ **initial classfile bytes của lần define hoặc redefine gần nhất**, JVM tái sử dụng kết quả không-capable rồi gọi lại nhóm capable. Ngoài ra, initial classfile bytes ở lượt sau có thể **không bit-identical** với file ban đầu vì JVM được phép tái bố trí constant pool hoặc lược bỏ một số attributes. Vì thế không nên nhận diện bản đã transform chỉ bằng SHA-256 của bytes đang được callback nhận.

Nếu muốn tránh chèn trùng helper, hãy xây biến đổi **idempotent** theo method name/descriptor/instruction pattern và kiểm thử lặp retransform trên JVM thực tế.

## 9. `ClassFileLoadHook` không phải callback vô hại

Một callback native nằm trong đường định nghĩa lớp; sai sót C/C++ có thể gây hậu quả lớn hơn Java exception thông thường:

- `strcmp(NULL, "...")` có thể crash JVM.
- Đọc vượt `class_data_len` hoặc dereference `class_data` không hợp lệ có thể dẫn đến lỗi native memory.
- Giữ `jobject`/`jclass` tham chiếu ngoài lifetime của JNI local reference mà không quản lý global reference có thể gây lỗi khó dự đoán.
- Log/serialize/đọc file trong callback có thể tạo lock contention, I/O latency và thậm chí trigger Java class loading trong điều kiện nhạy cảm.
- Không đồng bộ dữ liệu giữa callbacks đa luồng có thể tạo race. Đừng giả định JVM chỉ gọi ClassFileLoadHook trên một global thread.
- Một JNI call ở primordial có thể không hợp lệ vì `JNIEnv` null hoặc VM chưa ready.
- Trả classfile bytes không hợp lệ khiến load/redefine/retransform lỗi dù algorithm ứng dụng không đổi.
- Lưu quá nhiều raw class bytes có thể làm tăng bộ nhớ và lộ dữ liệu nhạy cảm trong constant pool.

**Thiết kế production** nên lọc rất sớm theo `name`, chỉ dùng metadata nhỏ, tránh I/O trên hot path, có bounds cho buffer/sampling, xử lý error code của mọi JVMTI operation và tách exporter ra khỏi callback. Nếu agent cần data chi tiết, chỉ phân tích classes mục tiêu và kiểm thử trên phiên bản JDK/VM thực tế.

### 9.1. Khi nào không nên dùng JVMTI trực tiếp?

Không phải bài toán telemetry nào cũng cần native agent. Nếu chỉ cần Java method tracing ở ứng dụng do mình kiểm soát, hãy cân nhắc logging, metrics, JFR hoặc `java.lang.instrument` trước. JVM TI đáng cân nhắc khi cần events và hooks native/tooling-level, debug sâu hoặc tính năng JVM không có API Java tương đương trực tiếp. Càng gần VM, trách nhiệm portability, memory management và phase correctness càng lớn.

## 10. Bảng lỗi và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| JVM báo không nạp được agent library | Sai absolute path, DLL/SO missing, sai bitness/ABI, thiếu dependencies | Kiểm tra `-agentpath`, kiến trúc, OS loader |
| `Agent_OnLoad` trả `JNI_ERR` | `GetEnv`, capability negotiation hoặc setup callback lỗi | In numeric `jvmtiError` trong pha setup; kiểm tra phiên bản API |
| Không thấy `JVMTI_HOOK=demo/Target` | Hook chưa bật, registration muộn, name filter sai, class đã load trước, VM-specific coverage | Kiểm tra `SetEventCallbacks`, `SetEventNotificationMode`, spelling `demo/Target` |
| `JVMTI_ERROR_WRONG_PHASE` | Gọi function sai giai đoạn | Dùng `GetPhase`; đối chiếu phase table trong spec |
| `JVMTI_ERROR_MUST_POSSESS_CAPABILITY` | Chưa xin capability trước thao tác | `GetPotentialCapabilities` + `AddCapabilities` + `GetCapabilities` |
| Event không có ở Primordial | Không xin đủ hai capabilities early/all | Cân nhắc xin sớm trong OnLoad nếu VM hỗ trợ; chịu được `JNIEnv == NULL` |
| Retransform không gọi hook agent A | A là retransformation-incapable | Phải xin `can_retransform_classes` trước lần enable đầu nếu muốn capable |
| Callback `name == NULL` | Tên không được chỉ định theo dạng thường | Luôn check null trước `strcmp` |
| Bytecode patch gây `VerifyError` | Output sai descriptor/stack/frame | Dùng bytecode toolkit và verifier, không sửa bytes thủ công |
| JVM crash ở callback | Native pointer/buffer/ref race hoặc C ABI sai | Native debugger, hs_err log, bounds checks, giảm công việc trong hook |
| Log quá nhiều khi startup | Callback nhận rất nhiều class events | Filter package/name, sampling, bounded counters |
| Cùng một lớp được hook nhiều lần | Redefine/retransform hoặc các lần định nghĩa bởi loaders khác | Phân biệt source, loader, phase, sequence; không coi callback = unique class |
| Cấu hình `-javaagent` nhưng C callback không chạy | Java agent JAR khác native JVMTI library | Dùng đúng `-agentpath`/`-agentlib` cho thư viện C |

Không nuốt mọi lỗi rồi coi như instrumentation đã thành công. **Không nhận event** khác với **nhận event nhưng trả no-op**, và cả hai khác với **nhận event nhưng class definition thất bại ở bước sau**.

## 11. Thực hành nâng cao và giới hạn chính xác

### 11.1. Quan sát thêm pha bằng `GetPhase`

Có thể thêm trong callback (vẫn chỉ trong phạm vi JVMTI functions cho phép):

~~~c
jvmtiPhase phase;
if ((*jvmti)->GetPhase(jvmti, &phase) == JVMTI_ERROR_NONE) {
    /* Ghi nhận mã phase vào counter/buffer native hữu hạn. */
}
~~~

Mảnh này không phải C program độc lập. Không nên `printf` mọi callback; một bộ đếm/buffer lock-free hoặc synchronization có chi phí giới hạn thích hợp hơn cho ứng dụng thật. Thông tin phase giúp giải thích tại sao JNI operation nào đó chưa sẵn.

### 11.2. Thử trường hợp `name == NULL`

Đừng cố tạo một lớp tên-null chỉ để chứng minh hook có thể nhận null nếu demo chưa cần. Unit test riêng cho hàm filter của C có thể gọi predicate với `NULL`, `"demo/Target"` và tên khác. Mục tiêu là test tính an toàn của code native ngay cả khi JVM không cung cấp tên.

### 11.3. Test capability theo pha

Một bài thử được kiểm soát có thể ghi `GetPotentialCapabilities` tại OnLoad, và so lại ở Live. Đừng giả định hai sets luôn trùng nhau. Không xin quá nhiều capabilities để “phủ mọi case”: chỉ xin feature cần thiết và kiểm tra `AddCapabilities` thành công trước khi bật corresponding event.

### 11.4. Test khi có nhiều agents

Nếu triển khai thêm một capable environment để retransformation, hãy kiểm tra số hook và bytes do mỗi environment nhận. Ghi rõ thứ tự tạo environments, thứ tự callback và xem output có bị chèn helper lặp lại không. Một event ở environment B có thể là output đã qua environment A, không chỉ baseline bytes.

## 12. Những nhầm lẫn phổ biến

1. **“JVM TI chính là JNI.”** Không: JNI gọi qua ranh giới Java/native; JVM TI cung cấp APIs/events cho tooling.
2. **“Có `jvmtiEnv*` là mọi thao tác đều được phép.”** Không: nhiều features cần optional capability và đúng phase.
3. **“GetPotentialCapabilities trả về capabilities đang sở hữu.”** Không: phải dùng `GetCapabilities` để xem cái đã được cấp.
4. **“AddCapabilities có thể gọi bất kỳ lúc nào để có mọi capability.”** Sai: một số chỉ xin được trong OnLoad hoặc bị hạn chế bởi VM/agents khác.
5. **“SetEventCallbacks xong tự nhận event.”** Không: cần `SetEventNotificationMode` để bật.
6. **“ClassFileLoadHook chỉ chạy một lần khi load class.”** Không: có thể chạy khi redefine/retransform.
7. **“Hook luôn thuộc Live.”** Không: có thể được gửi từ Start và trong Primordial với capabilities phù hợp.
8. **“Hook luôn có JNIEnv hợp lệ.”** Sai ở Primordial: có thể NULL.
9. **“name luôn là một chuỗi.”** Không: `name` có thể null; check trước khi so.
10. **“Có thể tự do `free` new_class_data.”** Không: output phải qua `Allocate` và JVM quản lý deallocation.
11. **“Bất kỳ class nào JVM tải đều phát hook giống nhau.”** Không: spec có class đặc biệt/optional coverage và timing.
12. **“Capable environment có thể đổi loại sau khi hook đã bật.”** Không: `can_retransform_classes` cần được cấp trước lần enable đầu.
13. **“Raw bytes nhận được luôn là .class trên đĩa.”** Không: có thể đã qua agent khác hoặc JVM tái tạo bytes ở retransform.
14. **“Một callback nghĩa là class đã load thành công.”** Không: callback trước khi classfile trở thành định nghĩa hoàn chỉnh.
15. **“Print từ hook không có overhead.”** Sai: synchronous I/O/locks có thể làm chậm class loading.
16. **“Native agent lỗi chỉ thành Java exception.”** Sai: lỗi bộ nhớ/ABI có thể crash cả JVM.
17. **“Java 17 không dùng được JVMTI.”** Sai: JDK 17 có JVMTI headers và native agent mechanism; cần compiler C phù hợp.
18. **“Phải sửa bytecode để chứng minh hook chạy.”** Không: chỉ quan sát `name` cũng đủ chứng minh callback được kích hoạt.

## 13. Checklist xây native agent có kiểm soát

1. Chọn đúng JVM vendor/version/OS/CPU architecture và headers tương ứng.
2. Dùng `-agentpath` với đường dẫn **absolute** nếu không cấu hình được library search path.
3. Viết `Agent_OnLoad` lấy `jvmtiEnv*` bằng `JavaVM::GetEnv`; kiểm tra return codes.
4. Gọi `GetPotentialCapabilities` và chỉ xin những bits cần thiết bằng `AddCapabilities`.
5. Nếu cần retransform-capable, cấp `can_retransform_classes` **trước khi bật hook lần đầu**.
6. Nếu cần primordial hook, xét đồng thời `can_generate_early_class_hook_events` và `can_generate_all_class_hook_events`.
7. Khởi tạo callback table sạch, gọi `SetEventCallbacks` rồi `SetEventNotificationMode` đúng event.
8. Trong callback, check `name != NULL`, filter theo internal name, không giữ raw pointer/objects lâu dài.
9. Không gọi JNI khi `jni_env` không sẵn hoặc phase không cho phép.
10. Khi trả modified classfile, cấp buffer bằng JVMTI `Allocate` và chỉ trả bytes hợp lệ; không sửa input buffer.
11. Tránh class-loader recursion, blocking I/O, large allocation và global locks trong hook.
12. Test startup bình thường, classload trước/sau hook, redefine/retransform nếu dùng, nhiều agents, custom loaders và failure path.
13. Quan sát lỗi setup tách biệt lỗi bytecode/linking/runtime, tránh báo một status “agent failed” chung.
14. Đo startup time, CPU, heap/native memory, GC, event throughput và độ trễ class loading.
15. Có giới hạn dữ liệu thu thập, không xuất bytecode chứa secrets và có cách gỡ agent/rollback cấu hình.

## 14. Câu hỏi tự kiểm tra

1. Trong một JVMTI agent, `jvmtiEnv*` khác `JNIEnv*` ở mục đích nào?
2. Năm phases là gì, và vì sao không nên so giá trị enum theo thứ tự số?
3. `VMStart` đánh dấu chuyển sang phase nào? `VMInit` đánh dấu chuyển sang phase nào?
4. `GetPotentialCapabilities` khác `GetCapabilities` ra sao?
5. Nếu agent cần `RetransformClasses`, phải cấp `can_retransform_classes` trước mốc nào?
6. Muốn nhận `ClassFileLoadHook` trong Primordial, cần kết hợp hai capabilities nào?
7. `SetEventCallbacks` đã đăng ký hàm, tại sao chưa chắc JVM gửi hook?
8. Trong `ClassFileLoadHook`, `name` dùng `demo.Target` hay `demo/Target`? Có thể null không?
9. `class_being_redefined` có giá trị gì khi load mới và khi redefine/retransform?
10. Vì sao không thể giữ `class_data` pointer qua nhiều threads để xử lý sau?
11. Agent phải cấp phát `new_class_data` bằng API nào, và ai giải phóng?
12. Vì sao output của một agent trong pipeline có thể là input của agent sau?
13. Một hook được gọi có chứng minh JVM cài class definition thành công không?
14. Vì sao demo không request `can_generate_early_class_hook_events`?
15. Chạy `java -cp out demo.Main` không agent tạo output gì, và vì sao không có JVMTI event log?
16. Những lỗi gì có thể đến từ sai native library bitness hoặc ABI?
17. Nếu thiếu trình biên dịch C nhưng có JDK, phần nào của demo vẫn kiểm chứng được?
18. Khi nào nên chọn `java.lang.instrument` hoặc JFR thay vì viết JVMTI native code?

## 15. Kết luận và nguồn chính thức

**JVM TI = native tooling API với capabilities và phases rõ ràng.** Một native agent phải lấy environment, xin quyền đúng lúc, đăng ký và bật event trước khi mong nhận callback. `ClassFileLoadHook` là mốc JVM có classfile bytes trước khi xây class representation; có thể xảy ra ở nhiều giai đoạn JVM và cả các phép redefine/retransform, chứ không chỉ ở Java application startup.

Ba quy tắc quan trọng nhất:

- **Capability không mặc nhiên có:** hỏi `GetPotentialCapabilities`, xin `AddCapabilities`, kiểm chứng `GetCapabilities` khi cần; riêng `can_retransform_classes` phải có trước lần bật hook đầu tiên nếu muốn environment capable.
- **Phase giới hạn điều được làm:** OnLoad, Primordial, Start, Live và Dead không cho cùng một tập functions; callback sớm có thể không có `JNIEnv` hợp lệ.
- **Callback có ranh giới ownership:** kiểm tra `name` nullable, giữ logic ngắn, không sửa raw input, và nếu trả class bytes mới thì cấp bằng JVMTI `Allocate` cho JVM quản lý.

Khi chỉ cần xem một lớp được JVM nạp lúc nào, native agent lọc một tên như `demo/Target` và không sửa bytes là đủ để hiểu cơ chế. Khi cần instrumentation production, hãy bổ sung parser/verification, chiến lược idempotence, quản lý native memory, giới hạn event volume, khả năng quan sát lỗi và kiểm thử đa JVM/OS.

### Tài liệu chính thức

- [Oracle JDK 21 — JVM Tool Interface](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): đặc tả JVMTI, phases, capabilities, events và lifecycle.
- [Oracle JDK 21 — Class File Load Hook](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#ClassFileLoadHook): chữ ký callback, timing, buffers, input/output và ordering.
- [Oracle JDK 21 — Capability Management](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#GetPotentialCapabilities): `GetPotentialCapabilities`, `AddCapabilities`, `GetCapabilities`.
- [Oracle JDK 21 — Get Phase](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#GetPhase): enum `jvmtiPhase` và các hàm tương ứng phase.
- [Oracle — The JVM Tool Interface: How VM Agents Work](https://www.oracle.com/technical-resources/articles/javase/jvm-tool-interface.html): ví dụ kiến trúc native tooling agent và event callbacks.
- [Oracle JDK 17 — Java Instrumentation package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): so sánh Java agent với native JVMTI agent.
