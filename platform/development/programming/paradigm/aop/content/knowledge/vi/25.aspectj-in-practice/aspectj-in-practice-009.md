# Khai báo liên kiểu và kiểm tra quy tắc ở bước xây dựng trong AspectJ

## 1. Vì sao AOP có thể thay đổi cả cấu trúc chương trình?

AOP thường được giới thiệu qua pointcut và advice: chọn một vị trí thực thi rồi chạy hành vi bổ sung trước, sau hoặc bao quanh vị trí đó. Đó là **crosscutting động** (*dynamic crosscutting*): chương trình có thêm xử lý khi chạy nhưng cấu trúc kiểu dữ liệu không nhất thiết thay đổi.

**AspectJ** còn cung cấp **crosscutting tĩnh** (*static crosscutting*), thực hiện khi biên dịch hoặc weaving. Hai nhóm khả năng nổi bật:

1. **Khai báo liên kiểu (inter-type declarations, ITD):** aspect có thể đưa method, field, constructor hoặc quan hệ kế thừa/triển khai interface vào kiểu khác. Các thành viên đó trở thành một phần của cấu trúc kiểu ở mã đã weave.
2. **Khai báo quy tắc xây dựng (declare error / declare warning):** aspect mô tả những join point mà quá trình xây dựng phải cảnh báo hoặc từ chối, ví dụ tầng giao diện không được gọi trực tiếp API lưu trữ.

Hai kỹ thuật này có mục đích khác nhau nhưng đều cho phép biểu đạt một quyết định kiến trúc tập trung. Advice chỉ chạy khi join point được thực thi; ITD và các kiểm tra declare error/warning tác động lên **kiểu hoặc quá trình build/weave**.

Ví dụ, một lớp Shipment ban đầu không khai báo interface Described. Aspect có thể bổ sung việc implement Described và một method describe(), sau đó code đã weave có thể gọi qua interface. Ngược lại, nếu quy tắc kiến trúc cấm ViewLayer gọi trực tiếp Repository.save(), declare error có thể khiến build thất bại ngay khi mã chứa lời gọi không hợp lệ, không cần chạy nhánh ấy.

**Mục tiêu bài học:** hiểu cú pháp và ngữ nghĩa của inter-type field/method/constructor, declare parents, declare error và declare warning; biết giới hạn truy cập/kiểu; tổ chức quy tắc build dễ hiểu và kiểm thử; phân biệt bảo đảm build với kiểm tra runtime.

## 2. Ôn lại các khái niệm AspectJ liên quan

- **Aspect:** đơn vị chứa pointcut, advice và các khai báo tĩnh xuyên suốt.
- **Join point:** vị trí được mô hình AOP nhận diện, như gọi hoặc thực thi phương thức.
- **Pointcut:** biểu thức chọn tập join point, dùng cho advice hoặc khai báo kiểm tra.
- **Advice:** đoạn mã chạy khi join point được chọn xảy ra.
- **Inter-type declaration:** khai báo trong aspect bổ sung thành viên hoặc cấu trúc kiểu khác.
- **Weaving:** bước hợp nhất aspect với các lớp liên quan, có thể tại compile time, sau compile hoặc load time tùy cơ chế.
- **Build-time architecture rule:** ràng buộc được kiểm tra khi biên dịch/weaving trên những join point mà compiler có thể phân tích.

Chẳng hạn:

~~~aspectj
before(): execution(* Shipment.process(..)) {
    System.out.println("before process");
}
~~~

Đây là **mảnh aspect minh họa**, giả định tồn tại kiểu Shipment có method process. Nó thể hiện dynamic crosscutting: trước mỗi execution join point phù hợp, advice được chạy.

Ngược lại:

~~~aspectj
public String Shipment.describe() {
    return "Shipment";
}
~~~

Đây là **inter-type method**, không phải advice. Nó khai báo thêm method trên Shipment ở chương trình đã weave. Muốn hoàn chỉnh cần đặt trong aspect và có lớp Shipment. Các ví dụ chạy đầy đủ ở phần sau.

## 3. Inter-type declarations thay đổi cấu trúc gì?

### 3.1. Thêm method vào kiểu khác

Cú pháp tổng quát:

~~~aspectj
[modifiers] ReturnType TargetType.methodName(Parameters) {
    // method body
}
~~~

Ví dụ:

~~~aspectj
public String Shipment.describe() {
    return "Shipment:" + id();
}
~~~

Đây là mảnh mã phụ thuộc lớp Shipment có method id(). Sau weaving, Shipment có method describe() dùng được theo quy tắc visibility. Từ khóa **this** trong thân method liên kiểu chỉ instance Shipment nhận lời gọi, **không** phải instance của aspect.

Nếu introduced method trùng chữ ký một thành viên đã có hoặc xung đột với các introduced member khác, compiler/weaver có thể báo lỗi. Không coi ITD như cơ chế tự động ghi đè bất kỳ method nào.

### 3.2. Thêm field

Cú pháp:

~~~aspectj
[modifiers] FieldType TargetType.fieldName = initialValue;
~~~

Ví dụ:

~~~aspectj
private int Shipment.readCounter = 0;
~~~

Một field instance mới được đưa vào mỗi instance Shipment đã weave. Trong AspectJ, thành viên liên kiểu private này có phạm vi truy cập theo **aspect khai báo**, tức code trong aspect được phép dùng nó. Field không trở thành biến chia sẻ toàn cục giữa mọi Shipment chỉ vì khai báo trong aspect.

Tuy nhiên, thêm state có thể ảnh hưởng bộ nhớ, thread-safety, serialization, thứ tự khởi tạo và bất biến của lớp. Với kiểu dữ liệu được chia sẻ qua nhiều luồng, một counter tăng bằng ++ không tự an toàn khi có cạnh tranh. Nên cân nhắc AtomicInteger hoặc thiết kế chuyên trách nếu cần số liệu đồng thời.

### 3.3. Thêm constructor

Cú pháp:

~~~aspectj
[modifiers] TargetType.new(Parameters) {
    // initialization
}
~~~

Ví dụ **chỉ minh họa**:

~~~aspectj
public Tag.new(String text) {
    this.text = text;
}
~~~

Đoạn này giả định Tag là class có field có thể gán text và không có constructor xung đột. AspectJ không cho khai báo constructor liên kiểu cho interface. Constructor introduced không thể dùng để gán field final được khai báo trong chính target type; do đó phải xem lại bất biến khởi tạo thay vì dùng ITD để tùy ý dựng object.

Cũng cần chú ý constructor không đối số: một class không khai báo constructor có thể đã có default no-arg constructor do Java tạo. Thêm constructor liên kiểu không đối số có thể xung đột dù file nguồn không có dòng constructor tường minh.

### 3.4. Thay quan hệ type bằng declare parents

Các dạng quan trọng:

~~~aspectj
declare parents: TargetTypePattern implements InterfaceType;
declare parents: TargetTypePattern extends SuperclassType;
~~~

**implements** dùng để làm một kiểu hoặc nhóm kiểu thực hiện thêm interface. **extends** thay đổi quan hệ superclass theo quy tắc và giới hạn hợp lệ của hệ thống kiểu Java/AspectJ; không thể tùy tiện phá bất biến kế thừa hoặc thêm nhiều superclass cho Java class.

Một ví dụ:

~~~aspectj
declare parents: Shipment implements Described;
public String Shipment.describe() {
    return "shipment:" + id();
}
~~~

Sau khi weave, Shipment thỏa hợp đồng Described. Nếu declare parents thêm interface có method trừu tượng chưa được class hoặc ITD đáp ứng, compiler/weaver có thể báo lỗi. Các giới hạn kiểu, truy cập và tương thích vẫn phải được đáp ứng; declare parents không phải thao tác ép kiểu runtime tùy ý.

## 4. Ví dụ chạy độc lập: thêm interface, field và method

Ví dụ sau dùng **code-style AspectJ**, gồm một file Java thuần và một file .aj. Java class không biết đến interface bổ sung trong mã nguồn riêng, nhưng sau compile-time weaving có thể được sử dụng như một Described.

### Tệp IntroDemo.java

~~~java
class Shipment {
    private final String code;

    Shipment(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}

interface Described {
    String describe();
}

public class IntroDemo {
    public static void main(String[] args) {
        Shipment shipment = new Shipment("S-7");
        Described described = shipment;
        System.out.println(described.describe());
        System.out.println("reads=" + shipment.readCount());
    }
}
~~~

### Tệp ShipmentIntroduction.aj

~~~aspectj
public aspect ShipmentIntroduction {
    declare parents: Shipment implements Described;

    private int Shipment.readCounter = 0;

    public String Shipment.describe() {
        this.readCounter++;
        return "Shipment:" + this.code();
    }

    public int Shipment.readCount() {
        return this.readCounter;
    }
}
~~~

### Biên dịch và chạy

Cần JDK 17+ và bộ công cụ **AspectJ ajc** có hỗ trợ nguồn Java 17. Cần thêm thư viện runtime AspectJ (aspectjrt.jar) của bộ phân phối tương thích. Đặt IntroDemo.java, ShipmentIntroduction.aj, aspectjrt.jar cùng thư mục.

Trên Linux/macOS:

~~~bash
mkdir -p out
ajc -17 -classpath aspectjrt.jar -d out IntroDemo.java ShipmentIntroduction.aj
java -cp out:aspectjrt.jar IntroDemo
~~~

Trên Windows PowerShell:

~~~powershell
mkdir out
ajc -17 -classpath aspectjrt.jar -d out IntroDemo.java ShipmentIntroduction.aj
java -cp "out;aspectjrt.jar" IntroDemo
~~~

**Kết quả chương trình dự kiến khi weaving thành công:**

~~~text
Shipment:S-7
reads=1
~~~

Giải thích:

1. File Java gốc chỉ khai báo Shipment, Described và IntroDemo, không khai báo implements hoặc describe() trên Shipment.
2. Aspect thêm interface Described vào Shipment thông qua declare parents, rồi thêm implementation describe().
3. Field readCounter được introduce riêng trên mỗi Shipment instance; mỗi lần gọi describe() tăng counter một đơn vị. readCount() trả số lượt đã gọi.
4. Vì compile-time weaving xử lý cả .java và .aj, compiler có thể type-check phép gán Described described = shipment và lời gọi shipment.readCount().
5. Nếu chỉ chạy javac trên tệp Java gốc mà không đưa aspect vào quá trình xây dựng, hai tham chiếu này không biên dịch được: Shipment chưa được Java thuần biết là Described và chưa có readCount().

**Giới hạn xác minh:** môi trường soạn nội dung hiện chưa có lệnh ajc, nên ví dụ và stdout được trình bày như kết quả dự kiến theo ngữ nghĩa AspectJ, không tuyên bố đã biên dịch/weave thực tế tại đây. Khi chạy bài thực hành, dùng ajc -version để xác nhận compiler và kiểm tra lỗi ở terminal trước khi đánh giá kết quả.

### Vì sao đây là static crosscutting?

Không có pointcut nào theo dõi thời điểm describe() được gọi để *tạo* method. Method và interface đã hiện diện trong cấu trúc type sau khi weave. Người đọc chỉ mở Shipment.java sẽ không thấy readCount() hoặc implements Described; để hiểu type thực tế phải xem cả ShipmentIntroduction.aj và cấu hình weave.

Đây vừa là lợi ích mở rộng hành vi không sửa lớp gốc, vừa là chi phí cần kiểm soát khi thiết kế module.

## 5. Giới hạn của inter-type declarations

### 5.1. Type phải thuộc tập code được weave

Việc một aspect khai báo bổ sung member cho một type không có nghĩa mọi bản triển khai/lớp đã biên dịch đang tồn tại đều tự được sửa. Compiler hoặc weaver phải thật sự nhận và xử lý bytecode/mã của target. Nếu một module khác tải bản Shipment chưa weave, nó không có hợp đồng Described được thêm theo cùng cách.

Điều này quan trọng khi các module được build riêng, đóng gói thư viện riêng hoặc có class loader khác nhau. Khi inter-type interface liên quan các implementation, interface và các class triển khai cấp đầu phải nhất quán với bản weave để tránh lỗi runtime do thiếu member.

### 5.2. Visibility không như viết source trực tiếp trong class

Member ITD có thể được khai báo public, private hoặc mức mặc định theo các quy tắc AspectJ. Với member private, phạm vi truy cập tương ứng với aspect khai báo; không nên nhầm với private member xuất hiện trực tiếp trong Java source của target. AspectJ không hỗ trợ protected inter-type member theo cùng cú pháp thông thường.

Tùy thiết kế, public introduced method sẽ xuất hiện trong API của type đã weave và có thể khiến client phụ thuộc vào aspect. Khi bỏ aspect, hợp đồng API này biến mất. Vì vậy, những API công khai cốt lõi nên được cân nhắc đặt trực tiếp trong module chủ sở hữu thay vì để một aspect tùy chọn introduce.

### 5.3. Xung đột thành viên, kế thừa và metadata

Nếu hai aspect introduce cùng public member hoặc một member trùng với target class, có thể phát sinh lỗi ambiguity/conflict. Với declare parents, Java chỉ có single inheritance cho class; quan hệ superclass/interface phải hợp lệ. Một interface mới cũng có thể thêm nghĩa vụ triển khai methods.

Thêm field có state tạo trách nhiệm khởi tạo và thread-safety. Dữ liệu serialize từ class sau weave có thể khác so với class chưa weave. Những thay đổi như vậy cần được quản lý như thay đổi kiểu/API, có kiểm thử tương thích.

### 5.4. Không dùng ITD để che giấu thay đổi domain lớn

Một introduced method tiện ích như describe() có thể giúp giảm boilerplate. Nhưng introduce các nghiệp vụ cốt lõi như calculateBalance(), transferOwnership() hoặc commitPayment() từ bên ngoài module domain có thể khiến bất biến bị phân tán. Người bảo trì khó biết logic quan trọng đang ở đâu và ai sở hữu nó.

Cần cân nhắc trước khi dùng ITD:

- Ai sở hữu contract mà member mới thực hiện?
- Việc đổi hoặc bỏ aspect có phá API của module không?
- Client có phải biết về kiểu đã weave để biên dịch không?
- Có thể dùng một adapter/decorator hoặc interface khai báo trực tiếp dễ hiểu hơn không?
- Mức độ truy cập vào state của type có tạo coupling với implementation nội bộ không?

ITD phù hợp khi thay đổi cấu trúc thật sự là một chính sách crosscutting tĩnh, tập target được kiểm soát và quá trình weaving là phần bắt buộc của build.

## 6. Kiểm tra quy tắc kiến trúc trong bước xây dựng

AspectJ cung cấp hai khai báo:

~~~aspectj
declare warning: PointcutExpression : "message";
declare error: PointcutExpression : "message";
~~~

Chúng yêu cầu compiler/weaver đưa ra cảnh báo hoặc lỗi khi phát hiện **join point có khả năng tồn tại** và khớp pointcut. Thay vì chờ đến runtime, build có thể phát hiện một đường phụ thuộc không hợp lệ trong mã.

Ví dụ chính sách: tầng giao diện chỉ được gọi tầng use case; không được gọi trực tiếp Repository.save(). Nếu một vị trí gọi từ ViewLayer tới Repository.save() xuất hiện trong code được weave, declare error sẽ chặn build.

### Điểm quan trọng về thời điểm kiểm tra

- **declare warning**: báo một vi phạm cần xem xét; chính sách build có thể quyết định cảnh báo có đủ để chặn pipeline không.
- **declare error**: báo lỗi compile/weave đối với join point bị chọn; build phải được xem là không hợp lệ.
- Pointcut kiểm tra được ở bước này phải dựa trên những yếu tố có thể quyết định tĩnh như kinded/scoping pointcuts: call(...), execution(...), within(...), withincode(...).
- Không thể yêu cầu declare error/warning ra quyết định dựa vào các yếu tố hoàn toàn runtime như cflow, cflowbelow, this, target, args, if. Những điều kiện này chỉ biết khi chương trình chạy nên không phù hợp để làm căn cứ compile-time check.
- Kiểm tra này chỉ bao phủ các join point **có mặt trong mã mà compiler/weaver nhìn thấy** và chọn được bằng pointcut. Nó không tự kiểm tra mọi module ngoài scope weaving hoặc lời gọi động/reflection tùy ý.

Điều này là **ràng buộc cấu trúc** chứ không phải thay thế kiểm thử nghiệp vụ, kiểm soát truy cập runtime hay phân tích bảo mật toàn diện.

## 7. Ví dụ quy tắc declare error: không đi tắt tầng kiến trúc

Giả định hệ thống có ba kiểu: Repository, UseCase và ViewLayer. ViewLayer chỉ gọi UseCase; UseCase mới gọi Repository.

### Tệp BoundaryDemo.java

~~~java
class Repository {
    void save(String value) {
        System.out.println("stored:" + value);
    }
}

class UseCase {
    private final Repository repository;

    UseCase(Repository repository) {
        this.repository = repository;
    }

    void execute(String value) {
        repository.save(value);
    }
}

class ViewLayer {
    private final UseCase useCase;

    ViewLayer(UseCase useCase) {
        this.useCase = useCase;
    }

    void submit(String value) {
        useCase.execute(value);
    }
}

public class BoundaryDemo {
    public static void main(String[] args) {
        Repository repository = new Repository();
        UseCase useCase = new UseCase(repository);
        ViewLayer view = new ViewLayer(useCase);
        view.submit("OK");
    }
}
~~~

### Tệp ArchitectureRules.aj

~~~aspectj
public aspect ArchitectureRules {
    declare error:
        call(* Repository.save(..)) && within(ViewLayer)
        : "ViewLayer must call UseCase, not Repository.save";

    declare warning:
        call(* Repository.save(..)) && within(BoundaryDemo)
        : "Move persistence calls into UseCase";
}
~~~

Giải thích các biểu thức:

- **call(* Repository.save(..))** chọn các vị trí gọi bất kỳ phương thức save có bất kỳ danh sách tham số phù hợp trong kiểu Repository, với return type bất kỳ.
- **within(ViewLayer)** yêu cầu vị trí gọi được khai báo trong mã của ViewLayer.
- Phép **&&** bắt buộc cả hai điều kiện cùng đúng.
- Vì mã hợp lệ chỉ gọi repository.save() từ UseCase.execute(), quy tắc cấm ở ViewLayer **không match**.
- declare warning thứ hai cho biết cách biểu diễn cảnh báo, nhưng ở bản code hợp lệ BoundaryDemo không gọi trực tiếp Repository.save(), nên nó cũng không match.

### Biên dịch bản hợp lệ

~~~bash
mkdir -p out
ajc -17 -classpath aspectjrt.jar -d out BoundaryDemo.java ArchitectureRules.aj
java -cp out:aspectjrt.jar BoundaryDemo
~~~

**Stdout chương trình dự kiến:**

~~~text
stored:OK
~~~

Để minh họa quy tắc bị vi phạm, thay riêng thân ViewLayer.submit() bằng đoạn sau rồi biên dịch lại:

~~~java
void submit(String value) {
    Repository bypass = new Repository();
    bypass.save(value);
}
~~~

Đây là **đoạn thay thế minh họa**, không phải một tệp đầy đủ. Khi compiler/weaver nhìn thấy lời gọi Repository.save() bên trong ViewLayer, điểm call khớp cả hai phần của declare error. Build phải thất bại với thông điệp được khai báo:

~~~text
ViewLayer must call UseCase, not Repository.save
~~~

**Không khẳng định toàn bộ console output đúng hệt một dòng:** định dạng thông báo lỗi, file/line, warning và mã lỗi phụ thuộc phiên bản/cấu hình ajc. Dòng trên là **phần thông điệp được khai báo**, không phải mô phỏng nguyên văn một phiên biên dịch đã chạy.

Điểm nổi bật: dù submit() chưa được thực thi trong thử nghiệm, một **lời gọi vi phạm có khả năng tồn tại trong mã được weave** đã đủ để declare error phát hiện. Kiểm tra ở đây không phải đánh giá biến value có bằng "OK" hay không; nó đánh giá vị trí phụ thuộc cấu trúc.

## 8. Viết pointcut kiến trúc chính xác và dễ duy trì

### 8.1. Chọn call thay vì execution để kiểm tra bên gọi

Nếu câu hỏi là “module A **có gọi** API của module B không?”, pointcut thường kết hợp **call(...)** với **within(...)** hoặc **withincode(...)** để xác định **vị trí bên gọi**.

~~~aspectj
declare error:
    call(* data.Repository+.save(..))
    && within(ui..*)
    : "UI must not call storage directly";
~~~

Đây là **mảnh cú pháp minh họa** với package/kiểu giả định data.Repository và ui... Dấu **+** sau type pattern bao gồm các subtype tương ứng; cần kiểm tra pattern so với chữ ký thực của call join point. Đừng sử dụng riêng execution(* Repository.save(..)) để suy ra ai đã gọi; execution chọn thân phương thức, không chỉ ra đường phụ thuộc từ UI.

Nếu muốn cấm một method trong chính module B không được thực thi, execution và within có thể phù hợp hơn. Phải xác định trước **loại sự vi phạm muốn phát hiện**.

### 8.2. Giới hạn theo module/package

Một quy tắc chọn toàn bộ project có thể bắt cả test, công cụ quản trị hoặc package được phép có ngoại lệ. Dùng within(module..*) hoặc những kiểu được chỉ định rõ để mô tả đúng phạm vi. Nếu có ngoại lệ hợp lệ, biểu diễn chúng tường minh, ví dụ loại trừ package bootstrap có trách nhiệm ghép mô-đun. Nhưng ngoại lệ quá rộng làm quy tắc mất giá trị.

Thay đổi package, di chuyển lớp hoặc chuyển từ lời gọi trực tiếp sang reflection có thể thay đổi tập match mà không đổi mục đích của code. Vì vậy mỗi rule cần có kiểm thử dương và âm: một mẫu hợp lệ được chấp nhận, một mẫu sai bị phát hiện.

### 8.3. Quy tắc không nên dựa vào trạng thái runtime

Ví dụ muốn cấm “người không có quyền ADMIN gọi save()” là **kiểm tra runtime authorization**; không thể dùng declare error để quyết định từ quyền của người dùng đang đăng nhập. Tương tự, liệu lời gọi xử lý sai dữ liệu, ghi trùng DB hay vượt hạn mức là câu hỏi runtime/domain.

Có thể dùng declare error để cấm **cấu trúc truy cập** trực tiếp đến API lưu dữ liệu, còn policy và dữ liệu nghiệp vụ vẫn phải được kiểm tra ở ranh giới thực thi phù hợp.

## 9. Những điểm thường bị bỏ sót khi dùng ITD và declare rule

### 9.1. Khả năng hiểu hành vi từ mã nguồn

Mở riêng Shipment.java không thấy interface/method mới; mở ViewLayer.java cũng chưa biết build bị chặn bởi quy tắc của ArchitectureRules. Muốn hiểu đầy đủ cần đọc thêm aspect và cấu hình build xác định tập weave.

Nên lưu một **bản đồ khai báo tĩnh** ở nơi dễ tìm:

| Target / vùng mã | Aspect áp dụng | Thay đổi hoặc quy tắc | Bằng chứng cần kiểm thử |
| --- | --- | --- | --- |
| Shipment | ShipmentIntroduction | Implements Described, describe(), readCounter, readCount() | Sau weaving có type/method và hành vi đúng |
| ViewLayer -> Repository | ArchitectureRules | declare error nếu gọi save trực tiếp | Mẫu sai không biên dịch |
| EntryPoint -> Repository | ArchitectureRules hoặc quy tắc tương tự | Có thể cảnh báo đường gọi cần xem xét | Mẫu hợp lệ và mẫu vi phạm đều được kiểm tra |
| Type hierarchy | declare parents | Thêm superinterface/superclass hợp lệ | Không có xung đột kiểu và API |

Bảng chỉ là mô hình minh họa; project thực phải ghi đúng tên type, phạm vi weaving và điều kiện kích hoạt.

### 9.2. Compile-time weaving so với load-time weaving

Các inter-type declarations và declare checks đòi hỏi compiler hoặc weaver thực sự nhìn thấy type/join point liên quan. Với **compile-time weaving**, nhiều vi phạm có thể được phát hiện trong quá trình build, phù hợp với mục tiêu chặn pull request sai kiến trúc. Với **load-time weaving**, một số thao tác phát hiện có thể xảy ra khi class được load; không được tự tuyên bố tất cả vi phạm đều đã được chứng minh ở bước build nếu chỉ weaving lúc runtime.

Nếu yêu cầu “build xanh đồng nghĩa không tồn tại lời gọi cấm”, cần bảo đảm quy tắc và toàn bộ tập class liên quan được đưa vào bước kiểm tra lúc build, không chỉ phân phối aspect jar và chờ runtime.

### 9.3. Các đường ngoài phạm vi weaving

Compiler không thể kết luận mọi thứ về mã không được weave, class được tạo động, native call, reflection hoặc dịch vụ chạy ở nơi khác. Một policy về phụ thuộc xuyên module có thể cần thêm module dependency rules, code review hoặc static analysis phù hợp. Không dùng declare error như lời bảo đảm bảo mật tuyệt đối.

### 9.4. Xung đột với Java type system

ITD tạo thêm API phải hợp lệ với Java: kiểu tham số/return, visibility, interface contract, field/method conflict, kế thừa và initialization. Compiler là công cụ phản hồi sớm, nhưng vẫn cần kiểm thử hành vi và tương thích binary. Nếu dùng JPMS, exports/opens và class loading cũng ảnh hưởng phạm vi tích hợp; không mở bừa package riêng tư chỉ để weaving thuận tiện.

### 9.5. Dùng warning có chủ đích

Warning thích hợp cho quá trình chuyển đổi một kiến trúc cũ, theo dõi API sắp loại bỏ hoặc báo đường gọi không mong muốn nhưng chưa thể sửa tất cả ngay. Error phù hợp với bất biến kiến trúc đã được thống nhất. Cần có chủ sở hữu rule, mô tả khắc phục rõ ràng, kiểm soát ngoại lệ và nâng warning thành error khi đủ điều kiện.

## 10. Thiết kế và kiểm thử các ràng buộc

Một quy trình thực tế:

1. **Xác định contract:** kiểu nào cần nhận member/interface mới? Biên giới module nào không được vượt?
2. **Viết rule theo ngôn ngữ cấu trúc:** quan hệ type cho declare parents; điểm gọi/định nghĩa cụ thể cho declare error/warning.
3. **Lắp đúng build:** compile/weave cả code cần sửa kiểu lẫn phần cần kiểm tra; xem thông báo compiler.
4. **Kiểm thử mẫu hợp lệ:** class đã weave gọi được member ITD, luồng hợp lệ không bị declare error bắt nhầm.
5. **Kiểm thử mẫu sai:** tạo một lời gọi trực tiếp bị cấm và bảo đảm bước build báo lỗi; tránh để mẫu sai nằm trong nguồn ứng dụng chính.
6. **Kiểm tra API:** introduced members có visibility/kiểu ổn định, không xung đột với code đang có.
7. **Kiểm tra runtime:** chức năng thật chạy đúng, aspect không đưa state nguy hiểm hoặc lỗi init.
8. **Tự động hóa:** đưa bước weave/rule-check vào build/CI; nếu có module mới, phải biết nó có được bao phủ không.
9. **Rà soát refactor:** đổi package, tên type hay dependency có làm pattern mất tác dụng hoặc chọn thêm type không mong muốn không?
10. **Tài liệu hóa:** ghi owner, phạm vi, thông điệp lỗi và cách sửa vi phạm.

Đối với mỗi declare error nên giữ một phép thử **negative compilation** riêng: nguồn sai phải bị compiler từ chối. Một bài kiểm thử chỉ chạy khi compile thành công không chứng minh rule sẽ chặn được vi phạm. Ngược lại, nếu compiler báo lỗi vì source Java sai cú pháp chứ không vì declare error, bài kiểm thử cũng chưa có giá trị; phải đối chiếu thông điệp mong đợi.

## 11. Phân biệt kiểm tra build với các chính sách runtime

| Nhu cầu | Công cụ/phạm vi thích hợp | Vì sao |
| --- | --- | --- |
| Bổ sung method/interface cho một type được weave | Inter-type declaration, declare parents | Thay cấu trúc type tĩnh |
| Cấm UI gọi Repository trực tiếp | declare error trên call + within | Vị trí gọi có thể nhận diện khi build |
| Cảnh báo API cũ còn được gọi | declare warning | Nhắc refactor dần |
| Kiểm tra quyền của người dùng đang đăng nhập | Runtime authorization/advice tại biên giới tin cậy | Chủ thể/quyền thay đổi ở runtime |
| Đo thời gian của một lần gọi | Advice + đồng hồ monotonic | Duration chỉ tồn tại khi thực thi |
| Quyết định đơn hàng có hợp lệ hay không | Domain logic | Phụ thuộc dữ liệu/trạng thái nghiệp vụ |
| Kiểm tra mọi module tuân thủ dependency direction | Rule AspectJ nếu các join point được bao phủ; có thể thêm dependency/static checks | Không phải mọi phụ thuộc đều là method-call join point |
| Đảm bảo code không lộ dữ liệu ở mọi nhánh | Kiểm thử bảo mật, policy và các kiểm soát khác | declare error không phân tích toàn bộ trạng thái runtime |

Không dùng ITD để thêm “thành công nghiệp vụ” vào một kiểu mà không xác định owner và contract. Không dùng declare error để suy ra rằng một người dùng cụ thể có quyền cập nhật bản ghi cụ thể. Kỹ thuật tĩnh làm tốt việc mô tả **cấu trúc**, còn yêu cầu runtime cần điểm kiểm tra runtime tương ứng.

## 12. Các lỗi hay gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ ITD là advice chạy mỗi lần gọi | Hiểu sai khi nào method/field xuất hiện | Phân biệt thay đổi type tĩnh và chạy advice động |
| Dùng javac thuần cho chương trình có .aj | Compiler không biết cú pháp/kết quả weave | Dùng ajc hoặc bước weaving tương đương |
| Chỉ weave aspect, không weave target | Type triển khai không có member mới | Đưa target vào phạm vi weaving |
| Introduce method trùng chữ ký | Lỗi thành viên hoặc ambiguity | Kiểm tra API và các aspect khác |
| Thêm constructor không đối số trùng default | Xung đột constructor | Xem cả constructor do Java tạo ngầm |
| Gán final field của target từ introduced constructor | Không hợp lệ | Khởi tạo trong owner hoặc dùng thiết kế khác |
| Dùng private ITD như private của target source | Hiểu sai phạm vi truy cập | Đọc visibility theo aspect khai báo |
| Dùng target/args/cflow trong declare error | Không thể quyết định thuần ở build time | Chọn PCD tĩnh: call/execution/within... |
| Dùng execution để phát hiện “UI gọi DB” | Không biết nguồn lời gọi | Dùng call kết hợp within phía UI |
| Để rule chỉ chạy ở load time nhưng khẳng định build chặn | Vi phạm có thể chỉ phát hiện khi chạy | Xác định compile-time weaving/check trong CI |
| Rule match quá rộng | Vi phạm giả, build bị chặn không cần thiết | Giới hạn type/package và kiểm thử ngoại lệ |
| Không có bài thử vi phạm | Rule có thể ngừng match sau refactor | Negative compilation test |
| Introduce state không đồng bộ | Race trên field giữa nhiều luồng | Xem thread-safety của member mới |
| Thay đổi public API qua aspect tùy chọn | Client phụ thuộc vào member có thể biến mất | Xem ITD là phần bắt buộc hoặc khai báo API trực tiếp |

## 13. Bài tập tự đánh giá

**Bài 1.** Một class Report có code cũ, cần implement interface Identifiable và cung cấp method id(). Hãy nêu cách dùng declare parents và inter-type method; nếu Report đã có method id() không tương thích, điều gì có thể xảy ra?

**Bài 2.** Một field counter được introduce dưới dạng private int Report.counter = 0. Field đó thuộc mỗi object Report hay là state chung của aspect? Khi nhiều luồng tăng counter, cần xét điều gì?

**Bài 3.** Tại sao dùng declare error: call(* Repository.save(..)) && within(ViewLayer) có thể chặn vi phạm trước lúc chạy, còn điều kiện “người gọi có role ADMIN” không thể được quyết định tương tự ở build time?

**Bài 4.** Build chỉ sử dụng javac cho IntroDemo.java và không weave ShipmentIntroduction.aj. Dự đoán lỗi kiểu nào sẽ xảy ra, và vì sao?

**Bài 5.** Một thư viện thứ ba không được đưa vào compiler/weaver nhưng có đường gọi vi phạm. Build sạch có đủ chứng minh quy tắc kiến trúc toàn hệ thống đã đạt không? Nêu bước cần bổ sung.

**Định hướng trả lời:** (1) declare parents: Report implements Identifiable và method ITD tương thích hợp đồng; thành viên xung đột gây lỗi. (2) Field instance trên từng Report; ++ không tự an toàn với concurrency. (3) Quy tắc call/within là cấu trúc tĩnh, role của user là dữ liệu runtime. (4) Java thuần không biết các thành viên và quan hệ được introduce, nên các tham chiếu sẽ không compile. (5) Không; phải mở rộng phạm vi weaving/check hoặc dùng thêm công cụ phân tích phụ thuộc phù hợp.

## 14. Ghi nhớ

- **Inter-type declarations** thay đổi cấu trúc type: method, field, constructor và quan hệ kế thừa/interface.
- **declare parents** mô tả việc thêm extends/implements nhưng vẫn chịu ràng buộc của hệ thống kiểu.
- **declare error/warning** mô tả quy tắc join point tĩnh để compiler/weaver cảnh báo hoặc chặn.
- Với ranh giới **bên gọi -> bên nhận**, hãy xét **call(...) && within(...)** trước khi chọn execution(...).
- Điều kiện phụ thuộc runtime như **this, target, args, cflow, if** không phù hợp làm bộ lọc của declare error/warning.
- Tính hiệu lực phụ thuộc vào **tập class thực sự được weave** và thời điểm weaving; build rule chỉ mạnh bằng phạm vi kiểm tra của nó.
- Mọi thay đổi API qua ITD và mọi rule build cần owner, kiểm thử dương/âm và tài liệu hóa.

**Kết luận:** AspectJ có thể tổ chức không chỉ hành vi xuyên suốt lúc chạy mà còn cấu trúc type và quy tắc kiến trúc tại thời điểm xây dựng. Dùng ITD khi cần một thay đổi cấu trúc được quản lý rõ, và dùng declare error/warning để chuyển những ranh giới phụ thuộc có thể xác định tĩnh thành phản hồi compiler. Kết hợp với kiểm thử và phạm vi weaving đầy đủ, chương trình dễ bảo trì hơn và lỗi kiến trúc được phát hiện sớm.
