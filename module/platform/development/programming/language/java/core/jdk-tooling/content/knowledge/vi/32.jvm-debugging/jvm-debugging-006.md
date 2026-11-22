# Suspend policy trong Java debugging

## 1. Suspend policy là gì?

Trong Java Platform Debugger Architecture (JPDA), debugger có thể đăng ký các yêu cầu nhận sự kiện từ JVM đang được debug (debuggee). Ví dụ: breakpoint, method entry, method exit, exception, single-step, thread start hoặc class prepare.

Khi một sự kiện khớp với một EventRequest đang bật, JVM gửi một EventSet vào EventQueue của debugger. **Suspend policy** quyết định những thread nào trong debuggee bị tạm dừng khi EventSet đó được phát ra.

Suspend policy là thuộc tính của từng EventRequest trong Java Debug Interface (JDI). Nó quyết định mức độ dừng của chương trình tại một sự kiện để debugger có thể kiểm tra trạng thái thread, stack frame và dữ liệu runtime.

Dừng thread không đồng nghĩa với dừng hoặc kết thúc process Java. Sau khi debugger xử lý sự kiện và resume đúng cách, thread hoặc JVM tiếp tục chạy.

## 2. Ba suspend policy trong JDI

JDI định nghĩa ba hằng số trong interface EventRequest:

| Hằng số | Giá trị | Hành vi |
|---|---:|---|
| SUSPEND_NONE | 0 | Không tạm dừng thread nào khi event xảy ra. |
| SUSPEND_EVENT_THREAD | 1 | Chỉ tạm dừng thread phát sinh event. |
| SUSPEND_ALL | 2 | Tạm dừng tất cả thread trong target JVM. |

Các giá trị số là hằng số được JDI định nghĩa, không phải các mức ưu tiên do ứng dụng tự đặt.

**SUSPEND_ALL là mặc định** của một EventRequest nếu debugger không thiết lập chính sách khác.

### SUSPEND_NONE

Khi event xảy ra, JVM tiếp tục chạy tất cả thread. Debugger vẫn nhận được event nhưng trạng thái ứng dụng có thể thay đổi trước khi debugger xử lý xong.

Phù hợp với các công cụ giám sát hoặc thu thập sự kiện cần hạn chế ảnh hưởng đến ứng dụng. Không phù hợp nếu cần một stack trace ổn định tại chính thời điểm event xảy ra.

### SUSPEND_EVENT_THREAD

Chỉ thread tạo ra event bị dừng. Các thread còn lại tiếp tục chạy.

Phù hợp khi debug một luồng xử lý cụ thể trong ứng dụng nhiều thread, giảm thời gian dừng toàn bộ hệ thống. Cần lưu ý thread khác có thể tiếp tục thay đổi dữ liệu dùng chung trong lúc debugger đang kiểm tra thread bị dừng.

### SUSPEND_ALL

Tất cả thread của target JVM bị dừng khi event xảy ra.

Phù hợp khi cần kiểm tra trạng thái đồng thời của nhiều thread, xem quan hệ khóa hoặc so sánh stack trace trong cùng một thời điểm. Đổi lại, toàn bộ ứng dụng tạm ngừng tiến triển trong thời gian debugger giữ EventSet chưa được resume.

## 3. Chọn chính sách phù hợp

| Nhu cầu debug | Chính sách thường phù hợp | Lý do |
|---|---|---|
| Kiểm tra một breakpoint trong một thread | SUSPEND_EVENT_THREAD | Giữ thread tại breakpoint, cho các thread khác tiếp tục. |
| Kiểm tra deadlock hoặc quan hệ giữa nhiều thread | SUSPEND_ALL | Cần snapshot ổn định của các thread để xem trạng thái và lock. |
| Ghi nhận event mà không muốn dừng ứng dụng | SUSPEND_NONE | Hạn chế pause do debugger tạo ra. |
| Phân tích biến cục bộ và stack frame của event thread | SUSPEND_EVENT_THREAD hoặc SUSPEND_ALL | Thread cần được suspend để đọc stack frame. |
| Quan sát event trong ứng dụng có yêu cầu độ sẵn sàng cao | SUSPEND_NONE, nếu không cần đọc stack | Tránh làm gián đoạn luồng xử lý. |

Không có một policy tốt nhất cho mọi tình huống. Hãy chọn theo thông tin debugger cần đọc và mức độ chấp nhận pause của ứng dụng.

## 4. Thiết lập suspend policy cho EventRequest

JDI cung cấp phương thức setSuspendPolicy(int) trên EventRequest. Có thể áp dụng cho BreakpointRequest, ExceptionRequest, MethodEntryRequest, StepRequest và các loại request khác kế thừa EventRequest.

Ví dụ tạo breakpoint và chỉ dừng thread chạm breakpoint:

~~~java
BreakpointRequest breakpoint =
        eventRequestManager.createBreakpointRequest(location);

breakpoint.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
breakpoint.enable();
~~~

Nếu muốn dừng tất cả thread:

~~~java
breakpoint.setSuspendPolicy(EventRequest.SUSPEND_ALL);
breakpoint.enable();
~~~

Nếu chỉ cần nhận thông báo:

~~~java
breakpoint.setSuspendPolicy(EventRequest.SUSPEND_NONE);
breakpoint.enable();
~~~

**Thứ tự cấu hình rất quan trọng:** tạo request, thêm filter nếu cần, đặt suspend policy rồi mới enable request.

JDI chỉ cho phép gọi setSuspendPolicy khi request đang disabled. Nếu request đã enabled hoặc đã bị xóa, thao tác có thể ném InvalidRequestStateException. Nếu truyền một giá trị policy không hợp lệ, có thể nhận IllegalArgumentException.

Ví dụ áp dụng cho MethodEntryRequest:

~~~java
MethodEntryRequest methodEntry =
        eventRequestManager.createMethodEntryRequest();

methodEntry.addClassFilter("com.example.OrderService");
methodEntry.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
methodEntry.enable();
~~~

Filter giúp giới hạn event theo class. Khi có nhiều event không liên quan, filter cũng giảm lượng event debugger phải xử lý.

## 5. EventSet và chính sách suspend thực tế

Các event được gửi tới debugger theo nhóm EventSet. Một EventSet có thể chứa nhiều event phát sinh tại cùng một thời điểm, ví dụ nhiều BreakpointEvent cùng location hoặc event liên quan đến cùng một lần thực thi.

Khi nhiều EventRequest cùng tạo event trong một EventSet, target JVM chọn policy có mức suspend rộng nhất trong các request đó:

- SUSPEND_NONE không dừng thread.
- SUSPEND_EVENT_THREAD dừng thread tạo event.
- SUSPEND_ALL dừng toàn bộ thread.

Vì vậy, nếu một event request dùng SUSPEND_NONE nhưng EventSet đồng thời chứa một event request dùng SUSPEND_ALL, policy thực tế của EventSet sẽ là SUSPEND_ALL.

Có thể đọc policy thực tế bằng:

~~~java
int actualPolicy = eventSet.suspendPolicy();
~~~

Trong trường hợp hiếm, policy thực tế có thể khác policy được yêu cầu nếu ClassPrepareEvent xảy ra trên debugger system thread. Khi xử lý EventSet, hãy dựa vào eventSet.suspendPolicy() để biết target JVM đã áp dụng chính sách nào.

## 6. Resume EventSet đúng cách

Sau khi debugger lấy EventSet từ EventQueue, phải giải phóng các thread đã bị suspend bởi event đó khi xử lý xong.

Cách thông thường:

~~~java
EventSet eventSet = vm.eventQueue().remove();

try {
    for (Event event : eventSet) {
        // Đọc và xử lý event tại đây.
    }
} finally {
    eventSet.resume();
}
~~~

EventSet.resume() có hành vi tương ứng với policy thực tế:

- SUSPEND_ALL: tương đương VirtualMachine.resume().
- SUSPEND_EVENT_THREAD: tương đương ThreadReference.resume() trên event thread.
- SUSPEND_NONE: không làm gì vì không có thread nào bị suspend bởi EventSet.

Dùng finally giúp đảm bảo EventSet được resume cả khi phần xử lý event gặp exception. Nếu EventSet không được resume, các thread do nó suspend có thể tiếp tục ở trạng thái dừng và target JVM có thể bị treo.

JDI khuyến nghị lấy và xử lý EventSet từ EventQueue cho đến khi nhận VMDisconnectEvent; mỗi EventSet cần được resume, trừ khi chương trình debugger đã quản lý việc resume theo một cơ chế khác.

## 7. Suspend count và việc resume nhiều lần

Suspend của thread và JVM được đếm theo số lần. Một thread có thể bị suspend bởi event, bởi VirtualMachine.suspend() hoặc ThreadReference.suspend().

Có thể kiểm tra:

~~~java
int count = thread.suspendCount();
boolean suspended = thread.isSuspended();
~~~

Mỗi lần suspend cần có một lần resume tương ứng trước khi thread có thể chạy lại. Nếu suspend count vẫn lớn hơn 0, một lần resume chưa chắc làm thread tiếp tục chạy.

Với suspension do EventSet tạo ra, cách thông thường là gọi EventSet.resume() để giải phóng đúng suspension của EventSet đó.

Không tùy tiện gọi ThreadReference.resume() hoặc VirtualMachine.resume() nhiều lần để ép ứng dụng chạy. Việc đó có thể làm lệch suspend count và giải phóng một suspension khác mà debugger hoặc công cụ đang quản lý.

## 8. Khả năng đọc stack frame theo từng policy

Để đọc stack frame của một thread bằng JDI, thread đó phải đang suspended.

Ví dụ:

~~~java
List<StackFrame> frames = thread.frames();
~~~

Nếu thread chưa suspended, JDI có thể ném IncompatibleThreadStateException.

Điều này tạo ra khác biệt thực tế:

- Với SUSPEND_NONE, thread tiếp tục chạy; debugger không thể dựa vào stack frame hiện tại để phân tích trạng thái tại event.
- Với SUSPEND_EVENT_THREAD, debugger có thể đọc stack của event thread. Thread khác vẫn chạy nên trạng thái dùng chung có thể thay đổi.
- Với SUSPEND_ALL, debugger có thể đọc stack của các thread đã bị dừng và so sánh chúng trong cùng một khoảng thời gian.

StackFrame chỉ có giá trị khi thread còn suspended. Sau khi thread resume, các StackFrame mirror trước đó không còn hợp lệ để tiếp tục dùng.

## 9. Deadlock và tác động khi chỉ suspend một thread

SUSPEND_EVENT_THREAD giúp giảm phạm vi pause nhưng có thể tạo tình huống deadlock tạm thời.

Ví dụ:

1. Thread A vào một synchronized block và giữ monitor M.
2. Thread A chạm breakpoint, debugger suspend riêng A.
3. Thread B tiếp tục chạy và cần monitor M.
4. Thread B phải chờ A nhả monitor.
5. Nếu debugger chờ kết quả từ Thread B trong khi vẫn giữ A suspended, việc debug có thể bị mắc kẹt.

Đây là lý do cần thận trọng khi suspend riêng một thread đang giữ lock hoặc tài nguyên mà thread khác cần.

SUSPEND_ALL dừng toàn bộ thread, nên các thread khác không tiếp tục chạy để tạo thêm cạnh tranh trong lúc debugger kiểm tra. Tuy nhiên, nó cũng giữ toàn bộ ứng dụng đứng yên cho đến khi resume; request kéo dài có thể làm tăng latency, timeout hoặc gián đoạn dịch vụ.

SUSPEND_NONE tránh pause do event nhưng debugger phải chấp nhận rằng ứng dụng vẫn đang thay đổi trong lúc đọc dữ liệu.

## 10. Suspend policy trong IDE và breakpoint

Nhiều IDE cho phép cấu hình suspend policy ngay trong thuộc tính breakpoint. Tên hiển thị có thể là:

- Suspend All: tương ứng SUSPEND_ALL.
- Suspend Thread: tương ứng SUSPEND_EVENT_THREAD.
- None: tương ứng SUSPEND_NONE.

Khi đặt breakpoint ở một dòng code, hãy kiểm tra policy nếu ứng dụng có nhiều thread.

Ví dụ, khi debug một request HTTP trong server:

- Suspend Thread giúp giữ thread đang xử lý request để xem biến và call stack.
- Suspend All giúp so sánh trạng thái các worker thread hoặc phân tích lock.
- None phù hợp với breakpoint/event dùng để quan sát mà không muốn dừng worker, nhưng không thể xem stack của thread đang chạy như một snapshot ổn định.

Một số IDE còn có tùy chọn log message hoặc evaluate expression khi breakpoint xảy ra. Những thao tác này không tự động làm thay đổi suspend policy; hãy kiểm tra cấu hình breakpoint riêng.

## 11. Phân biệt EventRequest policy với JDWP startup suspend

Có một cấu hình khác thường bị nhầm với suspend policy của breakpoint: tùy chọn suspend trong JDWP agent lúc khởi chạy JVM.

Ví dụ:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,address=localhost:5005,suspend=y com.example.Main
~~~

Tùy chọn suspend=y làm JVM phát VMStartEvent với policy SUSPEND_ALL. JVM bị suspend trước khi main class được nạp và chờ debugger kết nối rồi resume.

Nếu dùng:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,address=localhost:5005,suspend=n com.example.Main
~~~

JVM có thể bắt đầu thực thi trước khi debugger attach; VMStartEvent dùng SUSPEND_NONE.

Hai cơ chế khác nhau:

| Cấu hình | Phạm vi | Thời điểm |
|---|---|---|
| JDWP suspend=y/n | VMStartEvent khi khởi động | Khi debugger kết nối hoặc JVM bắt đầu chạy. |
| EventRequest.setSuspendPolicy(...) | Event do breakpoint, exception, step hoặc request khác tạo ra | Mỗi khi event tương ứng xảy ra. |

Đổi suspend policy của breakpoint không thay đổi tùy chọn suspend=y/n lúc JVM khởi động. Ngược lại, suspend=n không có nghĩa mọi breakpoint sau này đều dùng SUSPEND_NONE.

Với JDI LaunchingConnector, argument suspend=true mặc định yêu cầu target JVM tạm dừng ngay trước khi main class được nạp; debugger thường đăng ký event request rồi mới resume JVM.

## 12. Ví dụ thực hành: chương trình có hai thread

Tạo file **SuspendTarget.java**:

~~~java
public class SuspendTarget {
    static volatile boolean running = true;

    public static void main(String[] args) throws Exception {
        Thread worker = new Thread(() -> {
            while (running) {
                try {
                    Thread.sleep(10);
                } catch (InterruptedException ignored) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }, "policy-worker");

        worker.start();
        Thread.sleep(1500);
        hit();
        Thread.sleep(2500);

        running = false;
        worker.join();
    }

    static void hit() {
        // Method entry event được debugger theo dõi.
    }
}
~~~

Chương trình tạo thread policy-worker và sau đó gọi hit() trên main thread. Worker vẫn tồn tại khi main đi vào hit(), vì vậy debugger có thể quan sát sự khác nhau giữa các chính sách.

Tạo file **SuspendPolicyHarness.java**:

~~~java
import com.sun.jdi.Bootstrap;
import com.sun.jdi.ThreadReference;
import com.sun.jdi.VirtualMachine;
import com.sun.jdi.VMDisconnectedException;
import com.sun.jdi.connect.LaunchingConnector;
import com.sun.jdi.connect.Connector;
import com.sun.jdi.event.Event;
import com.sun.jdi.event.EventSet;
import com.sun.jdi.event.MethodEntryEvent;
import com.sun.jdi.event.VMDisconnectEvent;
import com.sun.jdi.event.VMDeathEvent;
import com.sun.jdi.request.EventRequest;
import com.sun.jdi.request.MethodEntryRequest;
import java.util.Map;

public class SuspendPolicyHarness {
    public static void main(String[] args) throws Exception {
        String policyName = args[0];

        int policy = switch (policyName) {
            case "NONE" -> EventRequest.SUSPEND_NONE;
            case "EVENT_THREAD" -> EventRequest.SUSPEND_EVENT_THREAD;
            case "ALL" -> EventRequest.SUSPEND_ALL;
            default -> throw new IllegalArgumentException(policyName);
        };

        LaunchingConnector connector =
                Bootstrap.virtualMachineManager().defaultConnector();

        Map<String, Connector.Argument> launchArgs =
                connector.defaultArguments();

        launchArgs.get("main").setValue("SuspendTarget");
        launchArgs.get("options").setValue("-cp " + args[1]);
        launchArgs.get("suspend").setValue("true");

        VirtualMachine vm = connector.launch(launchArgs);

        MethodEntryRequest request =
                vm.eventRequestManager().createMethodEntryRequest();

        request.addClassFilter("SuspendTarget");
        request.setSuspendPolicy(policy);
        request.enable();

        System.out.println("Requested policy: " + policyName);
        vm.resume();

        boolean found = false;

        while (!found) {
            EventSet eventSet = vm.eventQueue().remove(10000);

            if (eventSet == null) {
                throw new IllegalStateException("Timed out");
            }

            try {
                for (Event event : eventSet) {
                    if (event instanceof MethodEntryEvent methodEvent
                            && methodEvent.method().name().equals("hit")) {
                        found = true;

                        System.out.println(
                                "EventSet policy: " +
                                eventSet.suspendPolicy());

                        System.out.println(
                                "Event thread: " +
                                methodEvent.thread().name());

                        for (ThreadReference thread : vm.allThreads()) {
                            if (thread.name().equals("main")
                                    || thread.name().equals("policy-worker")) {
                                System.out.println(
                                        thread.name()
                                        + " suspended=" + thread.isSuspended()
                                        + " suspendCount=" + thread.suspendCount());
                            }
                        }
                    } else if (event instanceof VMDeathEvent
                            || event instanceof VMDisconnectEvent) {
                        throw new IllegalStateException(
                                "Target ended before hit event");
                    }
                }
            } finally {
                eventSet.resume();
            }
        }

        int exitCode = vm.process().waitFor();
        System.out.println("Target exit code: " + exitCode);

        try {
            vm.dispose();
        } catch (VMDisconnectedException expectedAfterTargetExit) {
            // Target đã kết thúc và đóng kết nối debugger.
        }
    }
}
~~~

Harness dùng MethodEntryRequest để quan sát lúc main đi vào hit(). MethodEntryRequest kế thừa EventRequest nên có thể thiết lập cùng ba suspend policy. Trong debugger thực tế, BreakpointRequest cũng dùng cùng cách cấu hình.

## 13. Biên dịch và chạy thử ba policy

Cần dùng JDK có module jdk.jdi. Mở terminal tại thư mục chứa hai file.

Biên dịch chương trình đích:

~~~bash
javac --release 17 -encoding UTF-8 SuspendTarget.java
~~~

Biên dịch debugger harness:

~~~bash
javac --release 17 --add-modules jdk.jdi -encoding UTF-8 SuspendPolicyHarness.java
~~~

Chạy từng policy:

~~~bash
java --add-modules jdk.jdi SuspendPolicyHarness NONE .
java --add-modules jdk.jdi SuspendPolicyHarness EVENT_THREAD .
java --add-modules jdk.jdi SuspendPolicyHarness ALL .
~~~

Mỗi lệnh khởi chạy một target JVM mới. Kết quả thực tế trên JDK 24.0.2:

~~~text
Requested policy: NONE
EventSet policy: 0
Event thread: main
main suspended=false suspendCount=0
policy-worker suspended=false suspendCount=0
Target exit code: 0

Requested policy: EVENT_THREAD
EventSet policy: 1
Event thread: main
main suspended=true suspendCount=1
policy-worker suspended=false suspendCount=0
Target exit code: 0

Requested policy: ALL
EventSet policy: 2
Event thread: main
main suspended=true suspendCount=1
policy-worker suspended=true suspendCount=1
Target exit code: 0
~~~

Kết quả cho thấy:

- NONE: cả main và policy-worker đều tiếp tục chạy.
- EVENT_THREAD: main bị suspend, policy-worker tiếp tục chạy.
- ALL: cả main và policy-worker đều bị suspend.
- Sau khi EventSet.resume() được gọi, target JVM tiếp tục và kết thúc với exit code 0.

Ví dụ đã được biên dịch bằng javac --release 17, chạy với module jdk.jdi trên JDK 24.0.2 và xác nhận kết quả của cả ba policy.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ứng dụng đứng sau khi breakpoint xảy ra | EventSet có SUSPEND_ALL hoặc SUSPEND_EVENT_THREAD nhưng chưa được resume. | Xử lý EventSet và gọi resume trong finally. |
| Thread khác vẫn chạy khi debugger đang dừng | Request dùng SUSPEND_EVENT_THREAD. | Chuyển sang SUSPEND_ALL nếu cần snapshot toàn JVM. |
| Không đọc được stack frame | Thread chưa suspended hoặc đã được resume. | Dùng policy phù hợp và đọc frames trước khi resume. |
| IncompatibleThreadStateException | Gọi frames() trên thread chưa suspend. | Kiểm tra isSuspended() và EventSet.suspendPolicy(). |
| setSuspendPolicy ném InvalidRequestStateException | Request đã enabled hoặc đã bị xóa. | Disable request, đặt policy rồi enable lại. |
| Thread khác bị block khi debug | Event thread bị suspend trong lúc giữ monitor. | Kiểm tra lock ownership; cân nhắc SUSPEND_ALL hoặc cách debug khác. |
| Ứng dụng tiếp tục thay đổi dữ liệu khi đang debug | Request dùng SUSPEND_NONE hoặc chỉ suspend event thread. | Dùng SUSPEND_ALL khi cần trạng thái đồng bộ. |
| Resume một lần nhưng thread vẫn đứng | Suspend count còn lớn hơn 0 do nhiều lần suspend. | Kiểm tra suspendCount() và cân bằng các lần resume. |
| Target không chạy main sau khi attach | JDWP startup suspend=y hoặc LaunchingConnector suspend=true chưa được resume. | Xử lý VMStartEvent và resume VM. |
| EventSet policy khác request policy | EventSet có nhiều request hoặc trường hợp đặc biệt của ClassPrepareEvent. | Kiểm tra policy thực tế bằng eventSet.suspendPolicy(). |

## 15. Quy trình debug có kiểm soát

Một quy trình dễ lặp lại:

1. Xác định event cần theo dõi: breakpoint, exception, method entry hoặc step.
2. Tạo EventRequest và thêm class/thread/count filter khi cần.
3. Chọn suspend policy theo mức độ quan sát cần thiết.
4. Đặt policy khi request còn disabled.
5. Enable request và bắt đầu nhận event.
6. Lấy EventSet từ EventQueue.
7. Kiểm tra eventSet.suspendPolicy() để biết policy thực tế.
8. Chỉ đọc stack frame của thread đang suspended.
9. Xử lý event trong phạm vi cần thiết và tránh giữ thread dừng quá lâu.
10. Gọi EventSet.resume() trong finally để giải phóng suspension.
11. Nếu thread vẫn dừng, kiểm tra suspendCount() và các lần suspend khác.
12. Gỡ hoặc disable request khi không còn cần theo dõi.

## 16. Bảo mật khi bật debugger

JDWP cho debugger khả năng điều khiển mạnh đối với JVM đích, bao gồm suspend thread, đọc stack và thay đổi trạng thái debug. Không mở cổng debug trên mạng công cộng hoặc mạng không tin cậy.

Khi cần attach từ xa:

- Chỉ bind vào loopback hoặc địa chỉ mạng quản trị đã được giới hạn.
- Dùng firewall hoặc allow-list để giới hạn địa chỉ debugger được phép kết nối.
- Áp dụng nguyên tắc least privilege: chỉ cấp quyền attach và quyền debug cho người cần thực hiện công việc.
- Tắt endpoint debug khi kết thúc phiên điều tra nếu môi trường không cần duy trì nó.
- Không chia sẻ địa chỉ hoặc cấu hình debug như một endpoint dịch vụ công khai.

Trên JDK 24, JDWP socket transport có tùy chọn allow để giới hạn địa chỉ client. Nếu không cần remote debugging, ưu tiên transport cục bộ.

## 17. Checklist khi chọn suspend policy

- [ ] Đã xác định rõ event request nào tạo ra event.
- [ ] Đã phân biệt SUSPEND_NONE, SUSPEND_EVENT_THREAD và SUSPEND_ALL.
- [ ] Đã biết mặc định của EventRequest là SUSPEND_ALL.
- [ ] Đã đặt policy trước khi enable request.
- [ ] Đã kiểm tra policy thực tế qua EventSet.suspendPolicy().
- [ ] Đã dùng EventSet.resume() để cân bằng event suspension.
- [ ] Đã kiểm tra suspendCount() nếu thread chưa tiếp tục chạy.
- [ ] Đã bảo đảm thread được suspend trước khi đọc stack frame.
- [ ] Đã cân nhắc deadlock khi suspend riêng thread đang giữ monitor.
- [ ] Đã đánh giá tác động khi dừng tất cả thread trên production.
- [ ] Đã phân biệt policy của event với JDWP startup suspend=y/n.
- [ ] Đã giới hạn quyền truy cập debugger theo nguyên tắc least privilege.
- [ ] Đã tắt hoặc xóa event request khi kết thúc phiên debug.

## 18. Tài liệu tham khảo

- Oracle Java SE 24 — JDI EventRequest: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jdi/com/sun/jdi/request/EventRequest.html
- Oracle Java SE 24 — JDI EventQueue: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jdi/com/sun/jdi/event/EventQueue.html
- Oracle Java SE 24 — JDI EventSet: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jdi/com/sun/jdi/event/EventSet.html
- Oracle Java SE 24 — JDI ThreadReference: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jdi/com/sun/jdi/ThreadReference.html
- Oracle JDK 24 — JPDA Connection and Invocation Details: https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html

Suspend policy điều khiển mức độ dừng của debuggee tại mỗi event request. SUSPEND_NONE giữ ứng dụng chạy, SUSPEND_EVENT_THREAD dừng thread phát sinh event, còn SUSPEND_ALL dừng toàn JVM. Chọn đúng policy, kiểm tra policy thực tế của EventSet và luôn resume đúng cách sẽ giúp debugger quan sát trạng thái cần thiết mà hạn chế pause ngoài ý muốn.