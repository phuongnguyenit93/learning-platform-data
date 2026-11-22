# Sai lầm: Dùng aspect cho mọi đoạn mã trùng mà không xét ý nghĩa

Khi học lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), một ý tưởng dễ gây hiểu nhầm là: “Đoạn mã xuất hiện ở nhiều nơi thì đưa ngay vào aspect để tránh lặp”. Sự lặp lại về **cú pháp** không có nghĩa là nhiều đoạn mã cùng thực hiện **một trách nhiệm**. AOP thích hợp khi một hành vi có ý nghĩa rõ ràng cần được áp dụng **xuyên suốt nhiều join point** theo quy tắc ổn định. AOP không phải cơ chế thay thế mặc định cho mọi hàm chung, lớp nghiệp vụ, chính sách miền hay phép trừu tượng hóa thông thường.

Ví dụ, hai phương thức đều có điều kiện “giá trị ít nhất 10”, nhưng một nơi là ngưỡng phân luồng vận chuyển theo khối lượng, nơi khác là ngưỡng hạng khách hàng theo số đơn hàng. Chúng trông giống nhau nhưng khác đơn vị đo, chủ thể quyết định, người sở hữu quy tắc, thông báo lỗi và lịch thay đổi. Đưa điều kiện đó thành một advice “áp dụng mọi nơi” sẽ trộn lẫn hai chính sách độc lập, khiến sửa quy tắc vận chuyển có thể vô tình đổi chính sách khách hàng.

Mục tiêu của bài là nhận diện **khi nào sự trùng lặp phản ánh một mối quan tâm xuyên suốt thực sự**, khi nào nó phản ánh logic miền riêng, và cách lựa chọn ranh giới aspect sao cho chương trình vẫn dễ hiểu, kiểm thử và thay đổi.

## 1. Phân biệt “mã giống nhau” và “một mối quan tâm xuyên suốt”

Một **mối quan tâm (concern)** là trách nhiệm hoặc lý do thay đổi của một phần chương trình. Hai đoạn mã có thể giống nhau ở hiện tại nhưng có **lý do thay đổi khác nhau**. Ngược lại, cùng một concern như ghi nhận thời gian thực thi có thể được cài đặt lặp lại ở nhiều phương thức khác nhau, đôi khi không giống từng ký tự.

Một **cross-cutting concern** thường cần hiện diện tại nhiều vị trí trong những lớp chức năng khác nhau, chẳng hạn đo độ trễ, thu thập dấu vết thực thi hoặc kiểm toán một loại thao tác đã được định nghĩa rõ. Trong AOP, logic này có thể được đóng gói bằng advice; pointcut chọn nơi áp dụng; weaving hoặc interception đưa advice vào quá trình chạy. Cơ chế AOP cụ thể quyết định loại join point có sẵn và giới hạn của advice.

Cần phân biệt ba câu hỏi:

1. **Trùng cú pháp?** Hai đoạn cùng dùng if, try/finally, phép so sánh, kiểm tra null hoặc cùng gọi một API.
2. **Trùng ý nghĩa và lý do thay đổi?** Cả hai có cùng chính sách, cùng chủ sở hữu, cùng tiêu chí đúng/sai và sẽ thay đổi đồng thời khi yêu cầu đổi không?
3. **Cần tác động xuyên suốt ở join point?** Hành vi đó có thể xác định bằng một hợp đồng điểm áp dụng rõ ràng, không phải bằng tên hàm hoặc biểu thức quá rộng, và có thể chèn mà không bóp méo logic nghiệp vụ không?

Câu trả lời “có” cho câu đầu tiên **không kéo theo** hai câu sau. Đôi khi chia sẻ một **hàm, giá trị miền, service hoặc thư viện** là hợp lý; đôi khi nên giữ hai đoạn mã riêng vì chúng chỉ giống nhau tình cờ. Aspect nên được chọn từ ý nghĩa và hợp đồng hành vi, không từ số lần một cấu trúc cú pháp lặp lại.

## 2. Ba dạng lặp cần xử lý khác nhau

| Dạng lặp | Ví dụ | Cách xử lý thường phù hợp | Vì sao |
| --- | --- | --- | --- |
| Giống cú pháp, khác chính sách | “>= 10” là kilogram trong giao vận, nhưng là số lần mua trong chương trình thưởng | Giữ chính sách trong đúng miền, dùng tên/kiểu dữ liệu rõ nghĩa | Hai quy tắc có thể thay đổi độc lập |
| Cùng logic miền thật sự | Nhiều luồng đều tính phí theo một bảng giá do cùng nhóm quản lý | Hàm miền, policy object, domain service hoặc thư viện chung | Nơi gọi cần biết công khai quy tắc nào được dùng |
| Cùng hành vi kỹ thuật xuyên suốt | Ghi metric thời gian cho mọi thao tác thuộc nhóm đã công bố | Aspect hoặc interceptor/decorator với pointcut chính xác | Hành vi bổ sung không thay nội dung quyết định nghiệp vụ |

Ngoài ra còn có **lặp vì công cụ hoặc kiến trúc**: mã chuyển đổi dữ liệu, triển khai giao diện, phần boilerplate. Tùy trường hợp, dùng helper, template method, code generation, composition hoặc một API rõ ràng. Việc loại lặp này xuất hiện nhiều nơi không tự chứng minh cần pointcut.

Một tiêu chí quan trọng là **quyền sở hữu và lý do thay đổi**. Nếu chính sách A thay đổi theo quy định giao vận còn chính sách B thay đổi theo chiến dịch khách hàng, chúng phải giữ khả năng thay đổi độc lập, dù hiện tại cùng biểu thức. Gộp chúng vào cùng aspect tạo ra coupling ẩn.

## 3. Vì sao lạm dụng aspect gây hại

### 3.1. Che khuất quy tắc nghiệp vụ

Khi phương thức tên calculateShipping chỉ nhìn thấy một lời gọi nghiệp vụ nhưng một advice tự động sửa giá trị, người đọc không thể hiểu đầy đủ quy tắc chỉ từ mã phương thức. Điều đó đặc biệt nguy hiểm với định giá, giới hạn số lượng, quyền truy cập, điều kiện hoàn tiền và các điều kiện kiểm tra đầu vào theo ngữ cảnh.

Aspect có thể phù hợp cho một chính sách bắt buộc **được định nghĩa và sở hữu tập trung**, nếu hợp đồng điểm áp dụng và semantics đã rõ. Nhưng **đưa mọi loại kiểm tra vào advice** khiến chính sách miền không còn ở vị trí cần được đánh giá trong luồng nghiệp vụ.

### 3.2. Ghép chung các lý do thay đổi độc lập

Một pointcut gom mọi phương thức có tiền tố validate, check hoặc calculate trông có vẻ tiện lợi. Tuy nhiên tên phương thức là dấu hiệu cấu trúc, chưa chắc phản ánh hợp đồng ngữ nghĩa. Đổi tên, thêm overload hoặc chuyển package có thể làm tập join point biến đổi ngoài ý muốn. Một chỉnh sửa nhỏ ở advice có thể ảnh hưởng cả nghiệp vụ không liên quan.

Mức độ rủi ro tăng theo **số join point × độ nhạy cảm ngữ nghĩa × mức khó phát hiện**. Cần giới hạn phạm vi aspect theo mục đích rõ ràng và có phép kiểm chứng điểm áp dụng.

### 3.3. Thêm hành vi không tường minh

Với advice dạng around, thứ tự thực thi, thời điểm tiếp tục lời gọi gốc, giá trị trả về, ngoại lệ và side effect đều có thể bị thay đổi bởi logic bao quanh. Cơ chế và ngôn ngữ AOP cụ thể quyết định cách tiếp tục lời gọi gốc hoạt động; không thể mặc định tất cả around advice có cùng semantics.

Một lời gọi tưởng là thuần tính toán có thể bất ngờ ghi file, mở kết nối, gọi API, retry hoặc thay tham số nếu logic này được đưa vào aspect. Cách làm đó khiến debugging khó hơn và phép kiểm thử unit vốn chỉ đọc mã nghiệp vụ không còn phản ánh đầy đủ hành vi runtime.

### 3.4. Làm pointcut quá rộng và tăng chi phí

Một biểu thức chọn “mọi phương thức” có thể bắt cả mã hạ tầng, test utilities, hàm trợ giúp và các lời gọi không cần quan sát. Tùy công cụ, advice có thể gây chi phí dispatch, đo đồng hồ, cấp phát, logging, lock hoặc I/O ở từng join point. Với tần suất cao, phần chi phí nhỏ mỗi lần có thể tích lũy đáng kể.

Nếu aspect bắt cả các lời gọi bên trong chính hệ thống logging/monitoring, có thể xuất hiện reentrancy, recursion hoặc nhân đôi sự kiện. Đây là hậu quả của việc chọn phạm vi theo hình dạng mã thay vì chủ đích.

### 3.5. Làm phụ thuộc vào cơ chế AOP bị che giấu

Một giải pháp dùng proxy chỉ quan sát những lời gọi đi qua proxy; lời gọi trực tiếp nội bộ có thể bỏ qua hành vi bổ sung. Một giải pháp weaving bytecode có tập join point và thời điểm tác động khác. Nếu thiết kế nghiệp vụ **đòi hỏi** một aspect chạy để quy tắc chính xác nhưng người viết code không biết giới hạn của cơ chế, hành vi có thể thay đổi theo đường gọi.

Với các điều kiện nghiệp vụ cốt lõi, cách biểu diễn trực tiếp bằng đối tượng miền hoặc service thường dễ chứng minh tính đúng đắn hơn. AOP cần một hợp đồng triển khai minh bạch nếu được dùng cho yêu cầu bắt buộc.

## 4. Tình huống trước–sau: cùng biểu thức, khác ý nghĩa

Giả sử một ứng dụng có hai quy tắc:

- Đơn hàng có khối lượng từ 10 kg trở lên được chuyển sang luồng FREIGHT; ít hơn đi PARCEL.
- Khách có ít nhất 10 đơn hàng hoàn tất đạt hạng GOLD; ít hơn có hạng STANDARD.

Hai điều kiện dùng toán tử và hằng số giống nhau, nhưng **kg** khác **completed orders**. Nếu tạo advice “mọi hàm có tham số số nguyên từ 10 trở lên áp dụng ưu đãi”, chúng ta đã nhầm tiêu chí kết hợp dữ liệu với tiêu chí kết hợp hành vi.

Phân tích quyết định:

| Câu hỏi | Vận chuyển | Hạng khách hàng |
| --- | --- | --- |
| Đơn vị đầu vào | Kilogram | Số đơn hoàn tất |
| Lý do thay đổi | Chính sách logistics | Chương trình khách hàng |
| Đầu ra | FREIGHT/PARCEL | GOLD/STANDARD |
| Ai sở hữu | Nhóm vận hành giao vận | Nhóm kinh doanh khách hàng |
| Có nên dùng chung một aspect điều kiện >= 10? | Không | Không |

Trong tình huống này, giữ mỗi quy tắc trong đúng đối tượng chính sách. Nếu quy tắc thực sự được dùng bởi nhiều luồng **cùng miền**, đưa nó vào một hàm miền hoặc policy được đặt tên rõ nghĩa. Không ép hai nghiệp vụ trùng cú pháp đi qua một aspect.

Ngược lại, nếu yêu cầu là **ghi một sự kiện rằng thao tác đã thành công hay lỗi** cho cả hai nhóm, đó có thể là concern xuyên suốt với hợp đồng độc lập. Advice có thể chèn chức năng ghi sự kiện mà **không quyết định** loại vận chuyển hay hạng khách hàng.

## 5. Ví dụ Java 17 chạy độc lập: quy tắc miền riêng, hành vi ghi nhận chung

Chương trình dưới đây dùng JDK dynamic proxy làm ví dụ **chặn lời gọi kiểu AOP**. Đây không phải một trình dệt bytecode tổng quát: nó chỉ minh họa interception các lời gọi đi qua interface do proxy triển khai. Logic miền vẫn nằm trong hai class riêng; phần ghi nhận kết quả lời gọi thành công/thất bại nằm ở một nơi chung.

Lưu file **MeaningBeforeAspect.java**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;

public class MeaningBeforeAspect {
    public interface Action {
        String perform(int value);
    }

    public static final class Shipping implements Action {
        @Override
        public String perform(int kilograms) {
            if (kilograms < 0) {
                throw new IllegalArgumentException("kg must be >= 0");
            }
            return kilograms >= 10 ? "FREIGHT" : "PARCEL";
        }
    }

    public static final class Loyalty implements Action {
        @Override
        public String perform(int completedOrders) {
            if (completedOrders < 0) {
                throw new IllegalArgumentException(
                        "orders must be >= 0");
            }
            return completedOrders >= 10 ? "GOLD" : "STANDARD";
        }
    }

    public static Action withAudit(Action target, List<String> events) {
        return (Action) Proxy.newProxyInstance(
                Action.class.getClassLoader(),
                new Class<?>[] { Action.class },
                (proxy, method, arguments) -> {
                    String name = target.getClass().getSimpleName();
                    try {
                        Object result = method.invoke(target, arguments);
                        events.add(name + ":OK");
                        return result;
                    } catch (InvocationTargetException ex) {
                        events.add(name + ":ERROR");
                        throw ex.getCause();
                    }
                });
    }

    public static void main(String[] args) {
        List<String> events = new ArrayList<>();

        Action shipping = withAudit(new Shipping(), events);
        Action loyalty = withAudit(new Loyalty(), events);

        System.out.println("Shipping: " + shipping.perform(12));
        System.out.println("Loyalty: " + loyalty.perform(12));

        try {
            shipping.perform(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }

        System.out.println("Events: " + events);
    }
}
```

Biên dịch, chạy bằng JDK 17 trở lên:

```bash
javac --release 17 MeaningBeforeAspect.java
java MeaningBeforeAspect
```

Kết quả:

```text
Shipping: FREIGHT
Loyalty: GOLD
Rejected: kg must be >= 0
Events: [Shipping:OK, Loyalty:OK, Shipping:ERROR]
```

**Điểm cần quan sát:**

1. Shipping và Loyalty cùng dùng ngưỡng 10 nhưng không chia sẻ policy vì ngữ nghĩa độc lập. Nếu sau này ngưỡng logistics đổi thành 15 kg, kết quả hạng khách hàng vẫn giữ nguyên.
2. Phần ghi nhận được áp dụng bên ngoài mã nghiệp vụ và **không thay đổi kết quả** của lời gọi thành công; ngoại lệ gốc được mở lại từ InvocationTargetException và chuyển tới caller.
3. List sự kiện chỉ là công cụ minh họa có tính xác định. Nếu dùng cho nhiều luồng đồng thời, phải chọn phương án ghi sự kiện thread-safe, hạn chế dữ liệu nhạy cảm và xử lý được lỗi của kênh ghi nhận.
4. Advice trong sản phẩm thực tế cần quy định rõ xử lý cả unchecked error, ngoại lệ từ chính hệ thống ghi log, lời gọi bất đồng bộ và các join point đặc biệt. Đoạn proxy này **không** định nghĩa chính sách đầy đủ cho các tình huống đó.
5. Đường gọi trực tiếp đến đối tượng Shipping không đi qua proxy sẽ không tạo sự kiện. Vì thế cần tài liệu hóa điểm áp dụng và test hợp đồng interception; không suy ra mọi lệnh gọi đều được chặn.

Để tự kiểm tra quyết định thiết kế, thử thay **chỉ** ngưỡng của Shipping thành 15 và chạy lại. Khi gọi shipping.perform(12), kết quả mới là PARCEL; Loyalty vẫn trả GOLD. Sự độc lập đó là một thuộc tính có chủ đích. Nếu ngưỡng bị nhét chung trong một aspect, yêu cầu “thay vận chuyển nhưng giữ chính sách khách hàng” trở nên khó thực hiện và khó kiểm thử hơn.

## 6. Khi nào nên chọn aspect?

Một aspect hợp lý thường trả lời rõ được cả bốn câu hỏi:

**(a) Hành vi này có một mục đích và một owner không?** Ví dụ “ghi metric thời lượng cho nhóm thao tác công khai” hoặc “thêm trace context vào các lời gọi được chỉ định” có chủ thể sở hữu và quy tắc đánh giá độc lập với phần lớn nghiệp vụ.

**(b) Có thể chọn join point theo hợp đồng ổn định không?** Dùng phạm vi package/interface/annotation/điểm gọi theo công cụ hỗ trợ hoặc danh sách explicit join point khi cần; không chọn chỉ vì những phương thức đang có vài dòng giống nhau. Tên và cấu trúc có thể dùng để biểu diễn một hợp đồng **đã được xác định bằng ngữ nghĩa**, chứ không phải nguồn tạo ra hợp đồng.

**(c) Advice có giữ đúng semantics nghiệp vụ không?** Với aspect mang tính quan sát, giá trị trả về, ngoại lệ, thứ tự side effect và số lần thực thi tác vụ gốc phải giữ nguyên theo yêu cầu. Với aspect cố ý thay đổi semantics, phải có hợp đồng nghiệp vụ rõ ràng, owner và phép kiểm chứng.

**(d) Có thể kiểm thử và vận hành độc lập không?** Có test pointcut matching và số lần advice chạy, có số đo chi phí, tài liệu hóa trình tự chạy và cơ chế debugging. Nếu câu trả lời là “chỉ hoạt động vì hiện các class trùng mẫu tên”, phạm vi aspect chưa đáng tin.

Một số trường hợp sử dụng có thể phù hợp:

- Thu thập thời gian thực thi/metric ở các đường gọi quan sát được và đã định nghĩa trước, với cardinality và sampling được kiểm soát.
- Ghi dấu kiểm toán cho **một nhóm thao tác được phân loại cụ thể**, khi cấu trúc sự kiện, quyền sở hữu và yêu cầu dữ liệu đã rõ.
- Thiết lập và dọn dẹp context của lời gọi trong một ranh giới kỹ thuật có hợp đồng nhất quán.
- Kiểm tra một quy tắc kỹ thuật chung tại nhiều entry point **chỉ khi** semantics, chính sách thất bại và điểm thực thi đã được xác nhận là giống nhau.

Ngay cả trong các trường hợp này, aspect là **một lựa chọn**, bên cạnh decorator, explicit interceptor hoặc các API được gọi trực tiếp. Có thể chọn giải pháp tường minh hơn nếu số điểm cần áp dụng ít, thay đổi giữa các trường hợp lớn hoặc cần hiện rõ luồng nghiệp vụ tại vị trí gọi.

## 7. Khi nào nên giữ logic ở hàm, lớp hoặc chính sách miền?

Các tín hiệu mạnh để **không tự động chuyển thành aspect**:

- Điều kiện dùng dữ liệu miền như giá, hạn mức, số lượng, trạng thái đơn hàng, chính sách hoàn tiền hoặc eligibility.
- Hai đoạn có cùng biểu thức nhưng được quyết định bởi các nhóm nghiệp vụ khác nhau.
- Người sửa cần nhìn trực tiếp rule khi đọc phương thức hoặc khi review nghiệp vụ.
- Các đường chạy cần thông báo lỗi khác nhau, xử lý ngoại lệ khác nhau hoặc cần truyền kết quả khác nhau.
- Chỉ có một vài nơi dùng, áp dụng bằng lời gọi tường minh dễ hiểu hơn pointcut.
- Kết quả phụ thuộc thứ tự các bước hoặc transaction boundary; “giấu” logic phía sau advice khiến thứ tự khó nhận biết.
- Muốn tái sử dụng cùng thuật toán có tham số cấu hình, nhưng chẳng có join point xuyên suốt phù hợp.

Nếu logic thuộc một miền và thật sự được chia sẻ, ưu tiên một **abstraction có tên nghiệp vụ**. Ví dụ ShippingPolicy.chooseRoute(weight) được nhiều luồng vận chuyển gọi; RewardPolicy.classify(completedOrders) được các luồng khách hàng gọi. Không nên tạo một UniversalThresholdAspect so sánh giá trị số bất kỳ với 10.

Nếu cần áp dụng hành vi bổ sung cho đúng **một đối tượng** thay vì chọn pointcut xuyên suốt, composition hoặc decorator có thể minh bạch hơn. Nếu mỗi use case chỉ có vài lời gọi và việc gọi policy chính là nội dung cần đọc hiểu, lời gọi tường minh thường hiệu quả hơn “ma thuật” chặn ngầm.

## 8. Quy trình phân tích đoạn mã trùng trước khi refactor

Đừng bắt đầu từ công cụ. Hãy bắt đầu từ **bản đồ trách nhiệm**:

1. **Liệt kê các vị trí trùng:** class/phương thức, đầu vào, đầu ra, ngoại lệ, side effect, caller và tần suất chạy. Đừng lấy việc giống một vài dòng làm kết luận.
2. **Viết lại mục đích bằng một câu nghiệp vụ:** “đo độ trễ của nhóm X” khác “chọn nhóm vận chuyển” dù cả hai cùng dùng if/try/finally.
3. **Hỏi về lý do thay đổi:** nếu chỉ một rule thay đổi, các đoạn kia có cần thay không? Nếu không, chúng không chia sẻ một chính sách duy nhất.
4. **Nhận diện owner và ranh giới:** ai phê duyệt logic, tiêu chí đúng/sai, thông báo lỗi và ngưỡng hiệu năng? Nếu owner khác nhau, cẩn trọng với một abstraction chung.
5. **Xác định điểm thực thi:** liệu có join point rõ ràng và được công cụ hỗ trợ? Có lời gọi bị bỏ sót do proxy, class loader, inlining hoặc mode weaving không?
6. **Chọn phương án nhỏ nhất đáp ứng ý nghĩa:** giữ nguyên nếu lặp ngẫu nhiên; trích hàm/kiểu miền nếu chung quy tắc; decorator/interceptor nếu chỉ cần wrap một ranh giới; aspect nếu concern cần áp dụng nhất quán ở nhiều join point.
7. **Xác minh semantics trước–sau:** so kết quả, ngoại lệ, side effect, thứ tự lời gọi và phân quyền; với aspect, test pointcut đúng cả trường hợp được chọn và trường hợp bị loại.
8. **Đo chi phí và tính dễ bảo trì:** benchmark nếu advice chạy thường xuyên, kiểm tra stack trace, khả năng tìm nguồn hành vi, độ phức tạp cấu hình và mức ảnh hưởng của mỗi lần sửa.

Đặt câu hỏi phản chứng quan trọng: **“Nếu hai đoạn code này ngày mai trông khác hẳn nhau nhưng vẫn cùng trách nhiệm, tôi có muốn áp dụng cùng advice không?”** Nếu có, đó là tín hiệu concern xuyên suốt đáng cân nhắc. Và **“Nếu hai đoạn vẫn giống nhau nhưng một yêu cầu nghiệp vụ thay đổi riêng, tôi có muốn chúng tách ra không?”** Nếu có, đừng gộp chỉ vì trùng cú pháp.

## 9. Pointcut dựa trên cấu trúc chỉ an toàn khi hợp đồng ngữ nghĩa đã rõ

Trong nhiều công cụ AOP, pointcut mô tả join point bằng biểu thức dựa trên tên, kiểu, package, annotation hoặc ngữ cảnh chạy. Cú pháp và tập join point được hỗ trợ tùy công cụ. Một selector cấu trúc có thể rất tiện nhưng không tự mang nghĩa nghiệp vụ.

Ví dụ có thể tồn tại nhiều phương thức có tên bắt đầu bằng validate, nhưng:

- validatePayment kiểm tra điều kiện thanh toán theo chính sách tài chính.
- validateStock kiểm tra số tồn kho theo thời điểm.
- validateMessageFormat kiểm tra cú pháp thông điệp.
- validateTelemetryPayload xác nhận cấu trúc dữ liệu quan sát.

Những phương thức này không có cùng error policy hoặc side effect. Pointcut kiểu “mọi validate*” không làm chúng có semantics giống nhau. Việc duy nhất chúng cùng tên chỉ là **đặc điểm chữ viết**.

Nếu thật sự có nhu cầu gắn advice kiểm toán cho một nhóm điểm vào hệ thống, hãy định nghĩa một **danh sách/nhóm thao tác được phê duyệt** và tạo test cho nó. Nếu chọn annotation làm dấu, annotation cũng phải có ngữ nghĩa rõ ràng, quy tắc sử dụng, review và test; biến mọi annotation thành một nhãn mơ hồ sẽ lặp lại lỗi thiết kế dưới hình thức khác.

Đồng thời cần để ý **thay đổi phạm vi theo thời gian**: thêm method mới trùng wildcard, chuyển package, sinh code tự động hoặc đổi loader có thể làm join point tăng/giảm. Các công cụ khác nhau có thể áp dụng aspect ở execution, call, constructor hay field access khác nhau; test phải phù hợp với khả năng thực tế của công cụ đã chọn.

## 10. Kiểm thử để phát hiện aspect bị dùng sai chỗ

Kiểm thử tốt phải phát hiện cả **áp dụng thiếu** lẫn **áp dụng thừa**.

| Loại kiểm thử | Mục đích | Ví dụ khẳng định |
| --- | --- | --- |
| Unit test nghiệp vụ không advice | Chứng minh chính sách miền tự thân đúng | Shipping ở 9/10/15 kg; Loyalty ở 9/10/15 đơn |
| Contract test pointcut | Đảm bảo đúng tập join point | Advice ghi metric chạy cho thao tác đã chọn, không chạy cho helper |
| Equivalence test | Advice kỹ thuật không đổi kết quả/ngoại lệ gốc | Bật/tắt advice trả cùng kết quả và cùng loại ngoại lệ |
| Advice ordering test | Phát hiện thay đổi thứ tự/tác dụng phụ | Kiểm toán được ghi ở giai đoạn hợp đồng yêu cầu |
| Integration test | Kiểm tra đường gọi và cơ chế áp dụng thực | Đường đi qua proxy/weaver đúng; không double advice |
| Concurrency test | Kiểm tra state dùng chung và context | Không rò context, race condition hay ghi đè sự kiện |
| Performance test | Đánh giá tác động khi join point nhiều | p95/p99, throughput, CPU, GC nằm trong ngưỡng |
| Change-isolation test | Chứng minh hai quy tắc giống cú pháp vẫn tách biệt | Đổi ngưỡng vận chuyển không đổi hạng khách |

Với aspect dạng quan sát, test nên kiểm tra **không can thiệp semantics** theo hợp đồng của thao tác gốc. Nếu yêu cầu thực tế cho phép advice chủ động ngắt, retry hay thay đổi kết quả, test phải mô tả rõ hành vi đó, số lần gọi gốc, cách xử lý ngoại lệ và ảnh hưởng lên side effect; đừng dùng khẩu hiệu “advice luôn trong suốt” khi bản thân yêu cầu không như vậy.

Để test ảnh hưởng của việc pointcut mở rộng, nên có các trường hợp **negative**: helper mới có tên giống tên nghiệp vụ, utility có cùng annotation sai mục đích, hoặc phương thức không thuộc nhóm được quan sát. Đây là cách phát hiện cấu hình AOP “bắt nhầm” mà test happy path không phát hiện được.

## 11. Dấu hiệu cần cảnh giác khi review AOP

| Dấu hiệu | Rủi ro | Câu hỏi review |
| --- | --- | --- |
| “Có ba đoạn if giống nhau nên làm aspect” | Đồng nhất nhầm chính sách | Có cùng owner và lý do thay đổi không? |
| Pointcut bắt toàn bộ class/method | Chi phí và side effect lan rộng | Tập join point chủ đích đã có test chưa? |
| Advice chứa bảng giá hoặc quy tắc phân loại | Ẩn miền trong hạ tầng | Quy tắc nên thuộc policy/service nào? |
| Advice thay tham số, kết quả hoặc ngoại lệ không được công bố | Phá hợp đồng caller | Có tài liệu và test semantics không? |
| Cùng một thay đổi làm hỏng hai nghiệp vụ độc lập | Coupling theo cấu trúc mã | Có cần tách owner và chính sách không? |
| Test một phương thức trực tiếp nhưng runtime gọi qua proxy | Độ phủ test không phản ánh đường chạy | Test đã chạy trên cơ chế áp dụng thật chưa? |
| Advice tự bắt hệ thống logging/telemetry | Recursion, log trùng, nghẽn tài nguyên | Có loại trừ mã hạ tầng và test số lần gọi không? |
| Một aspect chứa nhiều trách nhiệm không liên quan | Khó hiểu, khó rollback | Có thể chia theo từng concern và hợp đồng không? |
| Cần đọc nhiều cấu hình ngầm để hiểu một rule | Giảm khả năng bảo trì | Có cách biểu diễn trực tiếp dễ theo dõi hơn không? |

Đừng đánh giá chất lượng AOP bằng số dòng code bị xóa. Một refactor “giảm lặp” nhưng làm khó debug, tăng phụ thuộc và trộn chính sách có thể khiến **tổng chi phí bảo trì tăng**.

## 12. Tiêu chí quyết định và bài tập suy nghĩ

Trước khi tạo aspect mới, tự trả lời năm câu:

1. **Ý nghĩa:** Có thể đặt một tên concern độc lập với tên phương thức và cấu trúc if/try hiện tại không?
2. **Biên:** Có thể mô tả chính xác điểm nào phải nhận advice và điểm nào không, đồng thời kiểm thử hai tập đó không?
3. **Hợp đồng:** Giá trị trả về, ngoại lệ, thứ tự và side effect nào phải được giữ nguyên? Phần nào được chủ động thay đổi?
4. **Chủ sở hữu:** Khi business rule thay đổi, ai phê duyệt và phạm vi bị ảnh hưởng là gì?
5. **Giá trị ròng:** Lợi ích của việc tập trung hành vi có lớn hơn chi phí cấu hình ngầm, truy vết, testing và tài nguyên hay không?

Áp dụng cho các tình huống sau:

- **A:** Năm phương thức chuyển định dạng ngày cùng dùng quy tắc timezone do một thư viện chung quản lý. **Gợi ý:** ưu tiên utility/API chuyển đổi thống nhất nếu caller cần kết quả chuyển đổi; không nhất thiết cần aspect.
- **B:** Mười loại thao tác thuộc danh mục đã phê duyệt đều cần một bản ghi thời gian hoàn thành với cấu trúc giống nhau. **Gợi ý:** có thể dùng aspect nếu điểm áp dụng, trạng thái lỗi và cơ chế logging rõ ràng; kiểm thử không bắt nhầm thao tác ngoài danh mục.
- **C:** Hai nghiệp vụ dùng chung “nếu số lượng >= 10 thì đổi kết quả”, nhưng đơn vị đo và owner khác nhau. **Gợi ý:** giữ policy riêng, không gộp bằng điều kiện cú pháp.
- **D:** Một advice đang che giấu bước kiểm tra hạn mức riêng của từng loại giao dịch. **Gợi ý:** đưa rule về policy miền có tên; nếu tồn tại một điều kiện bảo vệ kỹ thuật chung thực sự, định nghĩa nó như concern độc lập và kiểm thử đầy đủ.

Quyết định cuối cùng phụ thuộc vào **ý nghĩa của hành vi và ranh giới thay đổi**, không phụ thuộc đơn thuần vào số dòng mã trùng. AOP đạt giá trị khi một concern xuyên suốt được đặt đúng chỗ, với pointcut có chủ đích và hợp đồng được kiểm chứng. Việc cố đưa mọi đoạn mã trùng vào aspect thường chỉ chuyển sự lặp nhìn thấy được thành phụ thuộc và hành vi ngầm khó phát hiện hơn.
