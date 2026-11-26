# Lựa chọn mô hình miền phong phú hoặc transaction script khi phù hợp

> Chương: **Tầng nghiệp vụ**

Trong module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, chúng ta học cách tổ chức phần mềm theo kiến trúc phân tầng. Bài này giúp lựa chọn cách biểu diễn logic nghiệp vụ trong tầng Business: dùng **mô hình miền phong phú (Rich Domain Model)** khi quy tắc và trạng thái cần được bảo vệ bởi các đối tượng nghiệp vụ, hoặc dùng **Transaction Script** khi một quy trình nghiệp vụ còn đơn giản và có thể diễn đạt rõ ràng bằng một thủ tục cho mỗi ca sử dụng.

Hai cách này là những lựa chọn thiết kế. Không có cách nào luôn đúng cho mọi hệ thống. Quyết định nên dựa trên độ phức tạp của quy tắc, số nơi sử dụng lại hành vi, cách trạng thái thay đổi và chi phí cấu trúc mà nhóm có thể duy trì.

## 1. Tầng nghiệp vụ cần giải quyết điều gì?

Tầng nghiệp vụ biểu diễn các quyết định và quy tắc tạo nên giá trị của hệ thống. Ví dụ trong ứng dụng ngân hàng, những quy tắc như số dư không được âm, tài khoản bị khóa không được chuyển tiền, hạn mức chuyển khoản mỗi ngày và phí giao dịch thuộc về nghiệp vụ. Trong ứng dụng bán hàng, quy tắc về giá, giảm giá, tồn kho, trạng thái đơn và điều kiện hoàn tiền cũng thuộc phạm vi này.

Presentation nhận yêu cầu và biểu diễn kết quả theo giao thức. Application điều phối một ca sử dụng: tải dữ liệu, gọi hành vi nghiệp vụ, lưu thay đổi và trả kết quả. Business/Domain là nơi thực thi các quy tắc nghiệp vụ. Infrastructure đảm nhận chi tiết kỹ thuật như SQL, JPA, message broker hoặc API của nhà cung cấp.

Trong một ứng dụng nhỏ, Application service và business service có thể được đặt gần nhau hoặc một lớp có thể đảm nhiệm nhiều vai trò. Điều cần quan tâm là quy tắc nghiệp vụ được đặt ở vị trí dễ hiểu, có thể kiểm thử và không bị phụ thuộc không cần thiết vào giao thức hay công nghệ lưu trữ.

## 2. Transaction Script là gì?

**Transaction Script** tổ chức logic nghiệp vụ thành các thủ tục, thường là một thủ tục cho mỗi ca sử dụng hoặc giao dịch nghiệp vụ. Thủ tục nhận dữ liệu đầu vào, tải dữ liệu cần thiết, thực hiện các bước và điều kiện nghiệp vụ, rồi lưu kết quả.

Với cách này, logic thường nằm trong một method của service hoặc business service. Các đối tượng dữ liệu có thể chủ yếu giữ dữ liệu và cung cấp getter/setter. Đây là lựa chọn dễ tiếp cận khi quy trình ngắn, ít quy tắc và thứ tự thao tác đã rõ.

Ví dụ: chuyển tiền từ tài khoản A sang tài khoản B. Với một quy trình đơn giản, service có thể thực hiện trực tiếp các bước:

```java
@Service
public class TransferMoneyScript {
    private final AccountRepository accounts;

    public TransferMoneyScript(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void transfer(TransferCommand command) {
        if (command.amount().signum() <= 0) {
            throw new InvalidTransferAmountException();
        }

        AccountData source = accounts.findData(command.sourceId())
            .orElseThrow(AccountNotFoundException::new);
        AccountData target = accounts.findData(command.targetId())
            .orElseThrow(AccountNotFoundException::new);

        if (source.isBlocked() || target.isBlocked()) {
            throw new AccountUnavailableException();
        }
        if (source.balance().compareTo(command.amount()) < 0) {
            throw new InsufficientFundsException();
        }

        source.setBalance(source.balance().subtract(command.amount()));
        target.setBalance(target.balance().add(command.amount()));

        accounts.save(source);
        accounts.save(target);
    }
}
```

Đây là ví dụ minh họa, trong đó `AccountData` là đối tượng dữ liệu đơn giản. Một thủ tục tập trung vào một mục tiêu: kiểm tra yêu cầu, lấy hai tài khoản, cập nhật số dư và lưu kết quả. Với một quy trình ít biến thể, người đọc có thể theo dõi toàn bộ logic tại một nơi.

Transaction Script có một số ưu điểm:

- Dễ viết và dễ đọc khi quy trình chỉ có vài bước.
- Ít cấu trúc phụ trợ, phù hợp với chức năng CRUD hoặc xử lý dữ liệu đơn giản.
- Dễ lần theo một ca sử dụng từ đầu đến cuối vì các bước nằm trong một method.
- Có thể kiểm thử bằng cách cung cấp repository giả và kiểm tra kết quả.

Nhược điểm xuất hiện khi quy tắc tăng lên. Nếu nhiều script cùng kiểm tra trạng thái tài khoản, tính phí, hạn mức và quyền giao dịch, logic có thể bị lặp. Khi quy tắc thay đổi, nhóm phải tìm và sửa mọi script liên quan. Method cũng có thể dài dần với nhiều nhánh điều kiện và khó xác định đâu là quy tắc dùng chung, đâu là trình tự riêng của ca sử dụng.

## 3. Mô hình miền phong phú là gì?

**Rich Domain Model** đặt dữ liệu cùng hành vi và quy tắc liên quan vào các đối tượng nghiệp vụ. Đối tượng không chỉ chứa trạng thái mà còn cung cấp các thao tác hợp lệ để thay đổi trạng thái đó. Những bất biến quan trọng được bảo vệ ngay tại nơi sở hữu dữ liệu.

Với ví dụ chuyển tiền, `BankAccount` có thể chịu trách nhiệm kiểm tra và thực hiện rút tiền hoặc nhận tiền. Bên ngoài không được tùy ý gán số dư mới:

```java
public class BankAccount {
    private final UUID id;
    private BigDecimal balance;
    private boolean blocked;

    public BankAccount(UUID id, BigDecimal openingBalance) {
        if (openingBalance.signum() < 0) {
            throw new InvalidOpeningBalanceException();
        }
        this.id = id;
        this.balance = openingBalance;
    }

    public void withdraw(BigDecimal amount) {
        requirePositive(amount);
        ensureAvailable();
        if (balance.compareTo(amount) < 0) {
            throw new InsufficientFundsException();
        }
        balance = balance.subtract(amount);
    }

    public void deposit(BigDecimal amount) {
        requirePositive(amount);
        ensureAvailable();
        balance = balance.add(amount);
    }

    private void requirePositive(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new InvalidTransferAmountException();
        }
    }

    private void ensureAvailable() {
        if (blocked) {
            throw new AccountUnavailableException();
        }
    }

    public UUID getId() { return id; }
    public BigDecimal getBalance() { return balance; }
}
```

Application service lúc này chủ yếu điều phối các đối tượng nghiệp vụ:

```java
@Service
public class TransferMoneyService {
    private final BankAccountRepository accounts;

    public TransferMoneyService(BankAccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void transfer(TransferCommand command) {
        BankAccount source = accounts.findById(command.sourceId())
            .orElseThrow(AccountNotFoundException::new);
        BankAccount target = accounts.findById(command.targetId())
            .orElseThrow(AccountNotFoundException::new);

        source.withdraw(command.amount());
        target.deposit(command.amount());
    }
}
```

Ví dụ đã lược bớt mapping và xử lý đồng thời để tập trung vào phân công trách nhiệm. `BankAccount` bảo vệ quy tắc rút và nhận tiền; service tải hai tài khoản rồi phối hợp hành vi. Với JPA, nếu hai tài khoản đang được quản lý trong persistence context, thay đổi có thể được lưu bằng dirty checking khi giao dịch flush. Nếu dùng cơ chế khác, repository có thể cần thao tác lưu tường minh.

Khi mô hình miền phong phú, một quy tắc được sử dụng từ nhiều ca sử dụng có thể nằm trong một hành vi chung. Ví dụ, chuyển tiền nội bộ, thanh toán khoản vay hoặc rút tiền đều có thể gọi `withdraw(...)`; mọi nơi đều phải tuân thủ cùng bất biến của tài khoản.

## 4. So sánh hai cách tổ chức

| Khía cạnh | Transaction Script | Rich Domain Model |
|---|---|---|
| Vị trí logic | Các thủ tục theo ca sử dụng | Hành vi nằm trong entity, value object hoặc domain service phù hợp |
| Đối tượng dữ liệu | Thường đơn giản, chủ yếu mang dữ liệu | Có trạng thái và hành vi bảo vệ bất biến |
| Tái sử dụng quy tắc | Có thể phải gọi hàm dùng chung hoặc tránh lặp giữa các script | Hành vi được đặt tại mô hình sở hữu quy tắc |
| Cách đọc luồng | Theo dõi từng thủ tục từ đầu đến cuối | Theo dõi sự phối hợp giữa các đối tượng và hành vi |
| Chi phí cấu trúc | Thấp khi quy trình đơn giản | Cao hơn do cần mô hình hóa và duy trì ranh giới đối tượng |
| Phù hợp khi | CRUD, báo cáo, quy trình ít nhánh và ít bất biến | Nhiều quy tắc tương tác, trạng thái phức tạp và hành vi được dùng ở nhiều nơi |

Không nên đánh giá Transaction Script là thiết kế kém hoặc Rich Domain Model là cấp độ trưởng thành bắt buộc. Một hệ thống có thể có nhiều phần với độ phức tạp khác nhau; chọn cách tổ chức phù hợp cho từng vùng nghiệp vụ thường thực tế hơn việc ép toàn bộ ứng dụng theo một kiểu.

## 5. Khi nào nên chọn Transaction Script?

Transaction Script thường là lựa chọn hợp lý khi:

- Quy trình có ít bước và các điều kiện nghiệp vụ khá trực tiếp.
- Dữ liệu chủ yếu được tạo, đọc, cập nhật hoặc xóa theo yêu cầu rõ ràng.
- Ít có bất biến cần được bảo vệ xuyên suốt vòng đời của một đối tượng.
- Mỗi chức năng có logic riêng, ít hành vi được chia sẻ giữa nhiều ca sử dụng.
- Nhóm cần giữ mã nguồn gọn và có thể hiểu nhanh luồng xử lý.

Ví dụ, một chức năng quản trị cập nhật địa chỉ giao hàng có thể chỉ cần xác thực định dạng, tải khách hàng, cập nhật các trường địa chỉ và lưu lại. Nếu không có nhiều quy tắc phụ thuộc lẫn nhau, việc tạo một mô hình miền lớn với nhiều object và interface có thể làm tăng số lớp mà không đem lại lợi ích tương xứng.

Transaction Script cũng phù hợp với các tác vụ nhập dữ liệu, xuất báo cáo hoặc chuyển đổi dữ liệu, nơi trọng tâm là quy trình xử lý và truy vấn hơn là một mô hình đối tượng có vòng đời nghiệp vụ phong phú. Dù vậy, các quy tắc quan trọng như phân quyền, tính hợp lệ hoặc giới hạn dữ liệu vẫn cần được đặt và kiểm thử rõ ràng.

## 6. Khi nào nên chọn Rich Domain Model?

Mô hình miền phong phú thường có lợi khi:

- Một đối tượng có nhiều trạng thái và chỉ được chuyển đổi theo những quy tắc nhất định.
- Nhiều quy tắc tương tác với nhau, chẳng hạn hạn mức, phí, thời điểm hiệu lực, quyền và trạng thái.
- Cùng một hành vi được sử dụng trong nhiều ca sử dụng hoặc nhiều điểm vào khác nhau.
- Thay đổi nghiệp vụ thường xuyên và cần tập trung quy tắc để tránh các bản sao không đồng nhất.
- Cần biểu diễn rõ khái niệm trong lĩnh vực để chuyên gia nghiệp vụ và lập trình viên cùng thảo luận.

Ví dụ, tài khoản ngân hàng có thể có trạng thái hoạt động, tạm khóa, đóng; có nhiều loại giao dịch, hạn mức theo ngày, phí theo loại khách hàng và quy tắc về số dư tối thiểu. Khi các quy tắc này cùng tác động đến việc rút, chuyển và thanh toán, việc đặt hành vi trong mô hình tài khoản hoặc domain service giúp bảo vệ tính nhất quán.

Mô hình miền phong phú không có nghĩa mọi class phải có hàng chục method, cũng không có nghĩa mọi phép gán đều phải được bọc trong một object riêng. Chỉ nên tạo hành vi và abstraction khi chúng biểu diễn một quy tắc hoặc ranh giới có ý nghĩa.

## 7. Đừng nhầm Transaction Script với database transaction

Hai thuật ngữ có từ “transaction” nhưng nói về hai khía cạnh khác nhau:

- **Transaction Script** là một mẫu tổ chức logic nghiệp vụ: một thủ tục thực hiện các bước của một ca sử dụng.
- **Database transaction** là cơ chế bảo đảm các thao tác dữ liệu tuân theo tính chất giao dịch, chẳng hạn commit hoặc rollback cùng nhau.

Một Transaction Script vẫn có thể chạy bên trong `@Transactional`. Một Application service điều phối Rich Domain Model cũng có thể chạy bên trong `@Transactional`. Chọn mô hình nghiệp vụ không quyết định việc có cần giao dịch cơ sở dữ liệu hay không; ranh giới giao dịch được xác định theo yêu cầu nhất quán dữ liệu của ca sử dụng.

Ví dụ, method `transfer(...)` trong Transaction Script ở trên dùng `@Transactional` để việc trừ tiền và cộng tiền được commit hoặc rollback cùng nhau. Trong ví dụ Rich Domain Model, service cũng dùng `@Transactional`, nhưng các quy tắc rút và nhận tiền được đặt trong `BankAccount`.

Giao dịch database cũng không tự bảo đảm xử lý đồng thời đúng trong mọi tình huống. Nếu hai request cùng đọc một số dư rồi cập nhật, hệ thống vẫn cần cơ chế phù hợp như optimistic locking, pessimistic locking hoặc cập nhật có điều kiện ở database. Đây là quyết định về nhất quán và lưu trữ, độc lập với cách tổ chức logic bằng script hay domain object.

## 8. Có thể kết hợp hai cách trong cùng hệ thống

Không nhất thiết phải chọn một kiểu duy nhất cho toàn bộ ứng dụng. Một hệ thống có thể dùng Rich Domain Model cho phần tài khoản và giao dịch tài chính, nơi nhiều bất biến cần được bảo vệ, nhưng dùng Transaction Script cho chức năng xuất báo cáo hoặc cập nhật cấu hình đơn giản.

Ngay trong một ca sử dụng, Application service vẫn có thể là một thủ tục điều phối ngắn, trong khi các quyết định nghiệp vụ được ủy quyền cho mô hình miền phong phú. Ví dụ `TransferMoneyService.transfer(...)` là một method theo trình tự của ca sử dụng, nhưng nó không tự sửa số dư; nó gọi `withdraw` và `deposit` trên domain objects. Điều này không biến toàn bộ hệ thống thành Transaction Script theo nghĩa mọi quy tắc đều nằm trong service.

Một cách kết hợp khác là giữ script cho quy trình đơn giản nhưng trích xuất một policy hoặc domain service cho quy tắc thực sự dùng chung. Không cần tạo một hệ thống object phức tạp chỉ để tránh một vài dòng điều kiện; mục tiêu là tránh lặp quy tắc có ý nghĩa và đặt chúng ở nơi sở hữu phù hợp.

## 9. Dấu hiệu cho thấy Transaction Script đang quá tải

Một script ban đầu ngắn có thể dần trở nên khó duy trì. Hãy chú ý các dấu hiệu:

- Nhiều service lặp lại cùng điều kiện về trạng thái, hạn mức hoặc tính hợp lệ.
- Một method có nhiều nhánh phụ thuộc lẫn nhau và khó mô tả bằng một mục tiêu rõ ràng.
- Một quy tắc thay đổi buộc phải sửa nhiều script và dễ bỏ sót một điểm gọi.
- Các đối tượng dữ liệu có nhiều setter công khai, khiến trạng thái có thể bị thay đổi theo những cách không hợp lệ.
- Các ca sử dụng khác nhau phải tự nhớ cùng một thứ tự kiểm tra để tránh phá vỡ bất biến.

Khi gặp các dấu hiệu này, hãy xác định đối tượng hoặc khái niệm nào thực sự sở hữu quy tắc. Chuyển hành vi liên quan vào entity, value object hoặc domain service; giới hạn setter để trạng thái chỉ thay đổi qua các hành vi hợp lệ; sau đó sửa từng script để gọi mô hình mới. Không cần chuyển đổi tất cả cùng lúc.

Ngược lại, nếu một Rich Domain Model có rất nhiều class, interface và lớp chuyển tiếp nhưng mỗi class chỉ giữ vài trường dữ liệu và không bảo vệ quy tắc nào, cấu trúc có thể đang phức tạp hơn nhu cầu. Khi đó, một script đơn giản hoặc một service gọn có thể dễ hiểu và rẻ hơn để duy trì.

## 10. Kiểm thử theo cách tổ chức đã chọn

Với **Transaction Script**, kiểm thử thường tập trung vào toàn bộ thủ tục: dữ liệu đầu vào, các trường hợp thành công/thất bại, repository được gọi và trạng thái cuối cùng. Có thể dùng fake hoặc mock cho repository để kiểm tra luồng mà không cần database thật.

Với **Rich Domain Model**, nên kiểm thử trực tiếp hành vi và bất biến của entity/value object/domain service. Ví dụ, kiểm tra tài khoản từ chối rút số tiền lớn hơn số dư, từ chối giao dịch khi bị khóa và cập nhật số dư đúng khi giao dịch hợp lệ. Các bài kiểm thử này thường không cần Spring context hoặc database.

Trong cả hai cách, vẫn cần kiểm thử tích hợp cho adapter persistence và ranh giới giao dịch. Unit test không chứng minh được mapping JPA, khóa đồng thời hoặc rollback trên database hoạt động đúng. Kiểm thử ở cấp Application cũng xác minh việc tải dữ liệu, phối hợp hành vi và lưu kết quả theo đúng ca sử dụng.

## 11. Cách đưa ra lựa chọn

Trước khi tạo nhiều lớp hoặc dồn logic vào một service, hãy tự hỏi:

1. Quy trình có bao nhiêu quy tắc và các quy tắc có phụ thuộc lẫn nhau không?
2. Trạng thái nào cần được bảo vệ để không rơi vào tình huống không hợp lệ?
3. Hành vi nào được sử dụng ở nhiều ca sử dụng hoặc nhiều điểm vào?
4. Logic có thường xuyên thay đổi theo chính sách nghiệp vụ không?
5. Chi phí mô hình hóa thêm có giúp giảm trùng lặp và làm rõ khái niệm không?

Nếu quy trình đơn giản, ít trạng thái và ít quy tắc chia sẻ, Transaction Script thường đủ dùng. Nếu quy tắc phức tạp, trạng thái có nhiều bất biến và hành vi được dùng ở nhiều nơi, Rich Domain Model thường giúp kiểm soát thay đổi tốt hơn. Nếu độ phức tạp nằm giữa hai trường hợp, hãy bắt đầu với cấu trúc đơn giản, quan sát nơi quy tắc lặp lại hoặc khó kiểm soát rồi trích xuất mô hình miền ở đúng điểm cần thiết.

## Ghi nhớ

- Transaction Script tổ chức logic thành thủ tục theo ca sử dụng; phù hợp với quy trình đơn giản và ít quy tắc tương tác.
- Rich Domain Model đặt trạng thái cùng hành vi bảo vệ bất biến trong entity, value object hoặc domain service phù hợp.
- `@Transactional` là cơ chế giao dịch dữ liệu, không phải định nghĩa của mẫu Transaction Script.
- Hai cách có thể cùng tồn tại trong một hệ thống; Application service vẫn có thể điều phối các hành vi của mô hình miền phong phú.
- Chọn cách tổ chức theo độ phức tạp nghiệp vụ, khả năng dùng chung quy tắc, nhu cầu thay đổi và chi phí duy trì; không có một mô hình bắt buộc cho mọi ứng dụng.
