# So sánh MVC và luồng dữ liệu một chiều

## Mục tiêu

Model–View–Controller (MVC) và luồng dữ liệu một chiều (Unidirectional Data Flow – UDF) đều giúp tổ chức ứng dụng giao diện, nhưng chúng nhấn mạnh hai khía cạnh khác nhau. MVC phân chia trách nhiệm giữa Model, View và Controller. UDF quy định cách sự kiện, trạng thái và giao diện thay đổi theo một hướng có thể theo dõi.

Trong ứng dụng web, MVC thường xuất hiện ở server: request đi vào Controller, Controller gọi nghiệp vụ và lấy dữ liệu, sau đó View tạo HTML trả về trình duyệt. UDF thường được dùng ở giao diện tương tác nhiều trạng thái: người dùng phát sinh action, logic cập nhật state, rồi View render từ state mới. Hai cách tiếp cận có thể kết hợp trong cùng một hệ thống.

Bài học này so sánh mô hình trách nhiệm, luồng request và state, cách xử lý sự kiện và tác dụng phụ, khả năng kiểm thử, độ phức tạp và trường hợp sử dụng. Ví dụ sử dụng Spring MVC ở phía server và reducer ở phía trình duyệt.

Sau khi học, người học có thể:

- Phân biệt MVC và UDF theo mục tiêu thiết kế.
- Mô tả luồng request trong MVC và luồng action–state–view trong UDF.
- Giải thích vị trí của Controller, Model, View, action, reducer và store.
- Nhận diện điểm mạnh, giới hạn và chi phí của từng cách tiếp cận.
- Tránh nhầm MVC với two-way data binding.
- Kết hợp MVC ở backend với UDF trong frontend.
- Chọn cách tổ chức phù hợp với quy mô và mức độ tương tác của ứng dụng.

## 1. Hai cách tiếp cận giải quyết hai câu hỏi khác nhau

MVC trả lời câu hỏi: **ứng dụng nên chia trách nhiệm giao diện và nghiệp vụ thành những thành phần nào?**

UDF trả lời câu hỏi: **một sự kiện làm thay đổi trạng thái và giao diện theo trình tự nào?**

Hai câu hỏi liên quan nhưng không đồng nhất. Một hệ thống có thể dùng MVC để tổ chức server-side và đồng thời dùng UDF để quản lý state trong một SPA. Vì vậy, không nên xem hai khái niệm như hai framework loại trừ nhau.

### MVC: phân chia trách nhiệm

MVC tổ chức ứng dụng quanh ba vai trò:

- **Model** quản lý dữ liệu, trạng thái và hành vi nghiệp vụ.
- **View** trình bày dữ liệu cho người dùng.
- **Controller** tiếp nhận tương tác hoặc request, điều phối xử lý và chọn phản hồi.

Trong ứng dụng web server-rendered, request thường đi qua Controller, gọi application service hoặc Model, sau đó trả dữ liệu cho template. View tạo HTML và gửi về browser.

### UDF: quy định hướng cập nhật state

UDF tổ chức việc cập nhật giao diện thành một chu trình rõ:

1. Người dùng tạo sự kiện.
2. Sự kiện được biểu diễn thành action hoặc message.
3. Logic cập nhật xử lý action và tạo state mới.
4. View render từ state mới.
5. Tương tác tiếp theo phát sinh action mới.

State được truyền xuống View; View phát sự kiện lên logic cập nhật. Dữ liệu trạng thái không bị thay đổi tùy tiện từ nhiều nơi.

    User event
        |
        v
      Action
        |
        v
    Update / Reducer
        |
        v
      New State
        |
        v
       View
        |
        +---- render UI
        |
        +---- user event mới ----> Action tiếp theo

UDF thường làm cho nguồn thay đổi state dễ xác định hơn. Khi giao diện hiển thị sai, nhóm phát triển có thể xem state hiện tại và action đã tạo ra state đó.

## 2. Luồng MVC trong ứng dụng web

Một ứng dụng Spring MVC server-side thường có luồng request–response:

    Browser
       |
       | HTTP request
       v
    DispatcherServlet / Router
       |
       v
    Controller
       |
       v
    Application Service
       |
       v
    Domain Model / Repository
       |
       v
    Application Result / View Model
       |
       v
    Controller
       |
       v
    View Template
       |
       | HTML response
       v
    Browser

Ví dụ người dùng gửi form cập nhật hồ sơ:

1. Browser gửi POST /profiles.
2. Spring Security kiểm tra authentication, authorization và CSRF theo cấu hình.
3. DispatcherServlet định tuyến đến Controller.
4. Controller nhận dữ liệu form và validation result.
5. Controller gọi application service để cập nhật hồ sơ.
6. Service gọi domain model và repository.
7. Controller chọn redirect hoặc View.
8. Template render kết quả thành HTML.

Controller là nơi tiếp nhận request và điều phối, nhưng không nên chứa toàn bộ quy tắc nghiệp vụ. Model/domain bảo vệ bất biến; application service tổ chức use case; repository xử lý lưu trữ.

### Một ví dụ Controller

    @Controller
    @RequestMapping("/profiles")
    public class ProfileController {
        private final UpdateProfile updateProfile;

        public ProfileController(UpdateProfile updateProfile) {
            this.updateProfile = updateProfile;
        }

        @PostMapping
        public String update(
                @Valid @ModelAttribute ProfileForm form,
                BindingResult errors,
                @AuthenticationPrincipal AppPrincipal principal) {

            if (errors.hasErrors()) {
                return "profiles/edit";
            }

            updateProfile.execute(
                    new UpdateProfileCommand(
                            principal.userId(),
                            form.displayName()));

            return "redirect:/profiles/me";
        }
    }

Ví dụ cho thấy Controller nhận input, xử lý lỗi binding và gọi use case. Quy tắc ai được cập nhật hồ sơ và cách thay đổi trạng thái thuộc application/domain layer. View template không trực tiếp ghi database.

### Request–response không có nghĩa toàn bộ Model phải được gửi về browser

Server thường chỉ gửi một View Model hoặc DTO chứa dữ liệu cần hiển thị. Entity nội bộ có thể có thông tin không nên công khai. View không cần biết toàn bộ cấu trúc persistence.

## 3. Luồng UDF trong giao diện tương tác

Trong UDF, View không tự ý sửa state dùng chung. View phát action thể hiện ý định; một reducer hoặc hàm update nhận state hiện tại cùng action và trả state mới.

    View
      |
      | dispatch(action)
      v
    Store / Update
      |
      | reducer(state, action)
      v
    New State
      |
      | subscribe / render
      v
    View

Ví dụ giỏ hàng có số lượng sản phẩm. Người dùng nhấn nút tăng số lượng:

- View phát action INCREASE_QUANTITY với productId.
- Reducer tìm sản phẩm và tạo state mới có quantity tăng một.
- Store công bố state mới.
- View render lại số lượng.

### Một reducer đơn giản

    const initialState = {
      items: [
        { id: "book-1", name: "Java Basics", quantity: 1 }
      ]
    };

    function cartReducer(state, action) {
      switch (action.type) {
        case "INCREASE_QUANTITY":
          return {
            ...state,
            items: state.items.map(item =>
              item.id === action.productId
                ? { ...item, quantity: item.quantity + 1 }
                : item
            )
          };

        case "DECREASE_QUANTITY":
          return {
            ...state,
            items: state.items.map(item =>
              item.id === action.productId
                ? { ...item, quantity: Math.max(1, item.quantity - 1) }
                : item
            )
          };

        default:
          return state;
      }
    }

Reducer nhận state và action, rồi trả một state mới. Nó không gọi API, không ghi local storage và không sửa trực tiếp state cũ. Những tác dụng phụ này được tổ chức ở một cơ chế effect hoặc middleware riêng.

### View render từ state

    function Cart({ state, dispatch }) {
      return state.items.map(item => (
        <div key={item.id}>
          <span>{item.name}</span>
          <span>{item.quantity}</span>
          <button onClick={() =>
            dispatch({
              type: "INCREASE_QUANTITY",
              productId: item.id
            })
          }>
            +
          </button>
        </div>
      ));
    }

View đọc state và phát action. Nó không tự tính toán rồi ghi trực tiếp vào một biến state dùng chung. Khi state thay đổi, framework render lại phần giao diện phụ thuộc state đó.

## 4. So sánh luồng thay đổi trong MVC và UDF

Cùng một thao tác “tăng số lượng sản phẩm” có thể được tổ chức theo hai cách.

### Trong MVC server-side

1. Người dùng nhấn nút tăng.
2. Browser gửi POST đến server.
3. Controller nhận product ID và số lượng hoặc ý định tăng.
4. Application service tải giỏ hàng và kiểm tra quyền.
5. Domain model tăng quantity theo quy tắc.
6. Repository lưu trạng thái.
7. Controller redirect hoặc render View mới.
8. Browser nhận HTML mới.

### Trong UDF phía client

1. Người dùng nhấn nút tăng.
2. View dispatch action.
3. Reducer tạo state giỏ hàng mới.
4. View render số lượng mới ngay trong browser.
5. Nếu cần lưu server, effect gửi command/API request.
6. Kết quả từ server trở thành action tiếp theo để cập nhật state.

| Khía cạnh | MVC server-rendered | UDF ở client |
|---|---|---|
| Sự kiện đầu vào | HTTP request | UI event/action |
| Nơi điều phối | Controller và application service | Store, reducer/update và effect |
| State chính | Thường nằm ở server/database hoặc session | Thường có bản state trong client store |
| Cập nhật giao diện | Server render HTML rồi trả response | View render lại từ state mới |
| Giao tiếp | Request–response | Action–state–view; có thể gọi API |
| Tính tương tác | Thường có round trip đến server | Có thể cập nhật tức thời ở client |
| Kiểm soát nghiệp vụ | Server/domain là nguồn quyết định | Client có thể dự đoán UI; server vẫn xác nhận nghiệp vụ |
| Phù hợp | Form, trang nội dung, quy trình server-driven | Giao diện nhiều state, tương tác liên tục |

Bảng này so sánh hai cách tổ chức phổ biến, không có nghĩa MVC bắt buộc phải round trip cho mọi tương tác hoặc UDF bắt buộc phải chạy hoàn toàn ở client.

## 5. MVC không đồng nghĩa với two-way data binding

Một nhầm lẫn thường gặp là cho rằng MVC luôn có luồng dữ liệu hai chiều. Điều đó không chính xác.

MVC mô tả vai trò và quan hệ giữa Model, View và Controller. Tùy framework, View có thể quan sát Model, Controller nhận sự kiện từ View, hoặc framework cung cấp binding tự động. Những cơ chế này là lựa chọn triển khai, không phải định nghĩa bắt buộc của MVC.

### Two-way binding là gì?

Two-way data binding đồng bộ giá trị giữa một control giao diện và một biến/model:

- Model đổi thì control hiển thị giá trị mới.
- Người dùng sửa control thì model được cập nhật theo binding.

Cơ chế này thuận tiện cho form đơn giản, nhưng nếu nhiều control và thành phần cùng sửa một state dùng chung, việc xác định nguồn thay đổi có thể khó hơn.

### MVC có thể dùng UDF

Controller có thể nhận một event, gọi hành vi Model, sau đó View render state mới. Đó là một luồng cập nhật có hướng rõ ràng bên trong một ứng dụng MVC.

Ngược lại, một ứng dụng UDF vẫn có thể chia code thành model/state, view và controller-like event handlers. Vì vậy, không nên kết luận rằng một ứng dụng có Controller thì không thể dùng UDF.

## 6. So sánh quyền sở hữu và vị trí của state

State là dữ liệu có thể thay đổi và ảnh hưởng đến giao diện hoặc hành vi.

Trong ứng dụng MVC server-side, nguồn dữ liệu có thẩm quyền thường nằm ở server: database, domain model, session hoặc application service. Browser gửi ý định và dữ liệu đầu vào; server kiểm tra rồi trả kết quả. Một số state tạm thời như trạng thái mở menu có thể nằm ở browser.

Trong UDF client-side, store hoặc component state giữ bản state mà giao diện đang render. Server vẫn là nguồn có thẩm quyền cho dữ liệu nghiệp vụ quan trọng. Client store có thể chứa bản sao hoặc projection của dữ liệu server để giao diện phản hồi nhanh.

| Loại state | Vị trí thường phù hợp | Ví dụ |
|---|---|---|
| Nghiệp vụ có thẩm quyền | Server/domain/database | Số dư, quyền sở hữu, trạng thái đơn hàng |
| Session/authentication | Server session hoặc identity provider; browser giữ credential theo cơ chế an toàn | Danh tính đăng nhập |
| State giao diện tạm thời | Component hoặc client store | Tab đang chọn, modal đang mở |
| Form draft | Form state phía client hoặc server session tùy nhu cầu | Nội dung chưa lưu |
| Server data cache | Query cache/client store hoặc cache server | Danh sách sản phẩm vừa tải |

### Tránh hai nguồn sự thật cùng ghi

Nếu client tự coi quantity là kết quả cuối cùng trong khi server có quy tắc tồn kho, hai phía có thể lệch nhau. Client có thể hiển thị dự đoán trước, nhưng server phải xác nhận kết quả nghiệp vụ và trả state đã được chấp nhận.

Một nguyên tắc hữu ích là phân biệt:

- **Optimistic state:** trạng thái tạm thời để giao diện phản hồi nhanh.
- **Confirmed state:** trạng thái server đã chấp nhận.

Nếu request thất bại, client cần rollback hoặc đồng bộ lại từ server.

## 7. Xử lý tác dụng phụ trong UDF

Reducer nên là hàm xác định: cùng state và action thì trả cùng kết quả, không gọi mạng hoặc thay đổi hệ thống bên ngoài. Tác dụng phụ như HTTP request, timer, local storage hoặc analytics nên được xử lý riêng.

Một luồng tải dữ liệu có thể là:

    User clicks Refresh
           |
           v
    dispatch(LOAD_ITEMS)
           |
           v
    Effect calls API
           |
           +---- success ----> dispatch(LOAD_ITEMS_SUCCEEDED)
           |
           +---- failure ----> dispatch(LOAD_ITEMS_FAILED)
                                  |
                                  v
                              New State
                                  |
                                  v
                                 View

State có thể biểu diễn trạng thái tải:

    const initialState = {
      items: [],
      status: "idle",
      error: null
    };

    function reducer(state, action) {
      switch (action.type) {
        case "LOAD_ITEMS":
          return {
            ...state,
            status: "loading",
            error: null
          };

        case "LOAD_ITEMS_SUCCEEDED":
          return {
            items: action.items,
            status: "succeeded",
            error: null
          };

        case "LOAD_ITEMS_FAILED":
          return {
            ...state,
            status: "failed",
            error: action.message
          };

        default:
          return state;
      }
    }

Effect thực hiện fetch và dispatch action kết quả. Reducer không tự gọi fetch. Nhờ vậy, state transition có thể được kiểm thử độc lập với mạng.

### Xử lý request đến sai thứ tự

Nếu người dùng gửi hai yêu cầu tìm kiếm liên tiếp, response của yêu cầu cũ có thể về sau response mới. Nếu reducer chấp nhận mọi response, kết quả cũ có thể ghi đè dữ liệu mới.

Có thể dùng request ID hoặc query key:

- Action LOAD_STARTED chứa requestId.
- Action LOAD_SUCCEEDED chứa cùng requestId.
- Reducer chỉ áp dụng kết quả nếu requestId còn là request hiện hành.

Cách này giúp state không bị cập nhật bởi response đã lỗi thời.

## 8. Xử lý tác dụng phụ trong MVC

MVC server-side cũng có tác dụng phụ, nhưng chúng thường được điều phối trong Controller/application service và tầng hạ tầng.

Ví dụ một request đặt hàng có thể:

1. Controller nhận command.
2. Application service kiểm tra quyền và điều phối use case.
3. Domain model tính toán và bảo vệ bất biến.
4. Repository lưu đơn hàng trong transaction.
5. Outbox ghi event trong cùng transaction.
6. Worker gửi thông báo sau commit.
7. Controller trả redirect hoặc response.

Controller không nên gọi email provider trước khi lưu thành công hoặc tự chứa toàn bộ transaction. Tác dụng phụ cần được đặt ở ranh giới phù hợp để bảo đảm độ tin cậy.

### Khác biệt chính

UDF tách side effect khỏi reducer để giữ state transition thuần và dễ kiểm thử. MVC thường tách side effect khỏi View/Controller thông qua application service, gateway, repository và event handling.

Cả hai đều có thể kiểm soát tác dụng phụ tốt nếu ranh giới được thiết kế rõ. Không nên cho rằng UDF không có side effect hoặc MVC luôn thực hiện side effect trực tiếp trong Controller.

## 9. So sánh khả năng kiểm thử và gỡ lỗi

### Kiểm thử MVC

Có thể kiểm thử theo từng lớp:

- Unit test cho domain rule và application service.
- Controller/MVC test cho binding, validation, route và response.
- Template test cho nội dung render.
- Integration test cho repository, transaction và security.
- End-to-end test cho luồng browser hoàn chỉnh.

Một test Controller có thể xác nhận request POST hợp lệ gọi use case và redirect đến trang chi tiết. Một unit test riêng xác nhận domain từ chối thao tác khi điều kiện không đáp ứng.

### Kiểm thử UDF

Có thể kiểm thử:

- Reducer với cặp state/action.
- Selector hoặc derived state.
- Effect với API giả lập.
- Component render theo state.
- Tương tác dispatch action.
- Luồng tích hợp từ event đến API result và state mới.

Ví dụ reducer test:

    test("increases quantity for the selected item", () => {
      const next = cartReducer(initialState, {
        type: "INCREASE_QUANTITY",
        productId: "book-1"
      });

      expect(next.items[0].quantity).toBe(2);
      expect(initialState.items[0].quantity).toBe(1);
    });

Test xác nhận state mới được tạo và state cũ không bị sửa trực tiếp.

### Gỡ lỗi

Trong MVC, có thể lần theo request ID qua Controller, service, repository và response. Lỗi thường được tìm bằng cách xác định request nào, use case nào và tầng nào thất bại.

Trong UDF, có thể xem action history, state trước/sau và reducer đã áp dụng. Nếu state transition được ghi nhận rõ, việc tái hiện lỗi UI thường dễ hơn.

| Tiêu chí | MVC | UDF |
|---|---|---|
| Đơn vị test quan trọng | Controller, use case, domain, repository, View | Reducer, effect, selector, component |
| Dữ liệu đầu vào | HTTP request, principal, Model | State và action |
| Quan sát luồng | Request trace/log | Action history/state transition |
| Test nghiệp vụ | Thường tập trung server/domain | Client test không thay thế server test |
| Lỗi tích hợp | Binding, routing, persistence, rendering | Async effect, stale response, state synchronization |

## 10. Độ phức tạp và chi phí tổ chức

MVC có thể rất gọn cho ứng dụng server-rendered. Một Controller nhận form, gọi use case và render template. Nếu trang có ít state tương tác, không cần store toàn cục hoặc hệ thống action phức tạp.

UDF có thể giúp ứng dụng nhiều state trở nên dễ dự đoán hơn, nhưng thêm khái niệm action, reducer, store, selector và effect. Với form đơn giản, những lớp này có thể làm code dài hơn mà không mang lại lợi ích tương xứng.

### Khi MVC trở nên khó quản lý

Một ứng dụng MVC có thể gặp vấn đề nếu:

- Controller chứa quá nhiều logic.
- View truy cập repository hoặc sửa dữ liệu trực tiếp.
- Model bị chia sẻ mutable state mà không có quy tắc.
- Nhiều lớp cùng cập nhật một trạng thái.
- Quy tắc nghiệp vụ bị lặp ở nhiều Controller.

Giải pháp thường là làm rõ application service, domain model, DTO và ranh giới persistence. Không nhất thiết phải thay toàn bộ ứng dụng bằng UDF.

### Khi UDF trở nên khó quản lý

Một ứng dụng UDF có thể gặp vấn đề nếu:

- Mọi state nhỏ đều được đưa vào global store.
- Action và reducer bị chia quá vụn.
- Side effect nằm trong reducer.
- Nhiều store giữ bản sao cùng một dữ liệu nhưng không đồng bộ.
- State được cập nhật qua quá nhiều lớp trung gian.
- Reducer chứa logic nghiệp vụ mà server cũng phải thực thi.

Giải pháp là xác định đúng phạm vi state, nhóm action theo use case và giữ nghiệp vụ có thẩm quyền ở server.

## 11. Ví dụ kết hợp MVC ở backend và UDF ở frontend

Một ứng dụng quản lý đơn hàng có thể dùng Spring MVC để cung cấp REST API và React reducer để quản lý state giao diện.

    Browser UI
       |
       | user event
       v
    Action / Dispatch
       |
       v
    Reducer / Client State
       |
       +---- render View
       |
       +---- Effect / API client
                  |
                  | HTTP request
                  v
             Spring MVC
                  |
                  v
              Controller
                  |
                  v
           Application Service
                  |
                  v
             Domain Model
                  |
                  v
               Database
                  |
                  v
             HTTP response
                  |
                  v
         API result action
                  |
                  v
             Reducer
                  |
                  v
             New UI state

Hai phía có trách nhiệm khác nhau:

- UDF quản lý trạng thái giao diện và chu trình tương tác trong browser.
- Spring MVC tiếp nhận request và tổ chức use case ở server.
- Domain model thực thi quy tắc nghiệp vụ có thẩm quyền.
- Database lưu trạng thái bền vững.
- API response đưa kết quả server về client.
- Reducer cập nhật client state từ kết quả đã xác nhận.

### Ví dụ API phía Spring MVC

    @RestController
    @RequestMapping("/api/cart")
    public class CartController {
        private final ChangeCartQuantity changeCartQuantity;

        public CartController(ChangeCartQuantity changeCartQuantity) {
            this.changeCartQuantity = changeCartQuantity;
        }

        @PatchMapping("/items/{itemId}")
        public CartResponse changeQuantity(
                @PathVariable UUID itemId,
                @RequestBody ChangeQuantityRequest request,
                @AuthenticationPrincipal AppPrincipal principal) {

            CartResult result = changeCartQuantity.execute(
                    new ChangeCartQuantityCommand(
                            principal.userId(),
                            itemId,
                            request.quantity()));

            return CartResponse.from(result);
        }
    }

Server lấy user ID từ principal, không tin user ID do client tự gửi. Application service kiểm tra quyền, tồn kho và quy tắc giỏ hàng rồi trả kết quả đã xác nhận.

### Ví dụ action phía client

    const action = {
      type: "CHANGE_QUANTITY_REQUESTED",
      itemId: "item-42",
      quantity: 3,
      requestId: "req-100"
    };

Effect gọi API:

    async function changeQuantityEffect(action, dispatch) {
      dispatch({
        type: "CHANGE_QUANTITY_STARTED",
        requestId: action.requestId
      });

      try {
        const response = await api.patch(
          "/api/cart/items/" + action.itemId,
          { quantity: action.quantity }
        );

        dispatch({
          type: "CHANGE_QUANTITY_SUCCEEDED",
          requestId: action.requestId,
          cart: response.data
        });
      } catch (error) {
        dispatch({
          type: "CHANGE_QUANTITY_FAILED",
          requestId: action.requestId,
          message: "Không thể cập nhật giỏ hàng."
        });
      }
    }

Reducer cập nhật state từ kết quả server. Nếu server từ chối vì hết hàng hoặc quyền không hợp lệ, client hiển thị lỗi và đồng bộ lại state. Không xem giá, quyền sở hữu hoặc tồn kho do browser gửi là dữ liệu đáng tin cậy.

### Vì sao kết hợp này hữu ích?

Người dùng có thể tương tác nhanh mà không cần server render toàn bộ trang sau mỗi thao tác. Server vẫn giữ quy tắc nghiệp vụ và dữ liệu có thẩm quyền. Mỗi phía có ranh giới rõ và có thể kiểm thử riêng.

## 12. So sánh khi chọn cho từng loại ứng dụng

| Tình huống | MVC server-rendered | UDF client-side |
|---|---|---|
| Trang nội dung, bài viết, trang giới thiệu | Phù hợp, đơn giản và dễ render từ server | Có thể dư thừa nếu ít tương tác |
| Form quản trị cơ bản | Phù hợp với binding, validation và redirect | Hữu ích nếu form có nhiều state động |
| Dashboard cập nhật liên tục | Có thể cần thêm AJAX hoặc polling | Phù hợp khi nhiều widget chia sẻ state |
| Trình chỉnh sửa nhiều bước | Có thể dùng session và server workflow | Phù hợp để quản lý draft, undo và step state |
| Giỏ hàng tương tác tức thời | Có thể xử lý bằng request/response | Phù hợp cho optimistic UI, nhưng server vẫn xác nhận |
| Ứng dụng offline-first | Cần bổ sung cơ chế client state và đồng bộ | Thường phù hợp hơn với state local và sync |
| Ứng dụng có SEO và nội dung server-driven | Thường thuận lợi | Có thể kết hợp server rendering/hydration |

Không có lựa chọn nào luôn tốt hơn. Hãy cân nhắc độ phức tạp của state, mức tương tác, yêu cầu SEO, khả năng offline, năng lực đội ngũ và cách hệ thống quản lý dữ liệu có thẩm quyền.

## 13. Những hiểu lầm cần tránh

### “MVC là luồng dữ liệu hai chiều”

MVC xác định trách nhiệm Model, View và Controller. Một framework có thể hỗ trợ binding hai chiều, nhưng đó không phải yêu cầu bắt buộc của MVC.

### “UDF là một framework cụ thể”

UDF là một cách tổ chức luồng sự kiện và state. Redux, reducer pattern hoặc kiến trúc MVI có thể áp dụng nguyên tắc tương tự theo những cách khác nhau.

### “UDF không cần backend kiểm tra”

Client state có thể bị sửa bởi người dùng hoặc script. Server vẫn phải kiểm tra authentication, authorization, validation, concurrency và quy tắc nghiệp vụ.

### “MVC không thể làm giao diện tương tác”

MVC có thể kết hợp JavaScript, AJAX, WebSocket hoặc frontend component. Vấn đề là chọn cách quản lý state phù hợp, không phải MVC cấm tương tác động.

### “Dùng store toàn cục sẽ làm ứng dụng dễ quản lý hơn”

Global store chỉ hữu ích khi state thực sự được chia sẻ hoặc cần quan sát tập trung. State cục bộ của một component không nhất thiết phải đưa vào store toàn ứng dụng.

### “Reducer có thể gọi API trực tiếp”

Nếu reducer gọi mạng hoặc thay đổi hệ thống bên ngoài, kết quả không còn thuần và khó kiểm thử. Hãy đặt tác dụng phụ trong effect hoặc middleware.

### “Client và server phải giữ state giống hệt nhau”

Client thường giữ một bản chiếu phục vụ giao diện. Server có thể có dữ liệu đầy đủ hơn và là nguồn có thẩm quyền. Cần quy tắc đồng bộ, xử lý conflict và trạng thái stale thay vì giả định hai bản luôn giống nhau.

## 14. Cách kết hợp hai cách tiếp cận mà không làm rối trách nhiệm

Một kiến trúc kết hợp có thể chia thành ba vùng:

**Backend MVC/application layer**

- Nhận HTTP request.
- Xác thực và phân quyền.
- Chuyển input thành command/query.
- Thực hiện use case và quy tắc domain.
- Lưu dữ liệu và trả response.

**Frontend UDF**

- Nhận event từ người dùng.
- Dispatch action.
- Quản lý state giao diện.
- Điều phối request bất đồng bộ qua effect.
- Render View từ state.

**Hợp đồng API**

- Định nghĩa request/response DTO.
- Dùng error code ổn định.
- Xác định semantics của thao tác và idempotency.
- Quy định pagination, versioning và conflict.
- Không để client tự quyết định dữ liệu đặc quyền.

### Quy tắc thực tế

- Backend là nguồn có thẩm quyền cho dữ liệu nghiệp vụ quan trọng.
- Frontend store quản lý trạng thái cần cho trải nghiệm giao diện.
- Controller không trở thành nơi chứa mọi quy tắc.
- Reducer không trở thành nơi thực hiện I/O.
- View chỉ trình bày state và phát sự kiện.
- API contract phải đủ rõ để hai phía phát triển độc lập.
- Khi server từ chối hoặc trả phiên bản mới hơn, client phải đồng bộ state theo response.

## 15. Quy trình lựa chọn

Khi thiết kế một chức năng mới, có thể đặt các câu hỏi theo trình tự:

1. Chức năng có chủ yếu là hiển thị nội dung và xử lý form request–response không?
2. Có nhiều thành phần giao diện cần chia sẻ state không?
3. Người dùng cần cập nhật UI tức thời trước khi server phản hồi không?
4. Có yêu cầu offline, undo/redo, optimistic update hoặc đồng bộ nhiều nguồn không?
5. Quy tắc nào phải được server xác nhận?
6. State nào chỉ thuộc giao diện và state nào là dữ liệu nghiệp vụ?
7. Có thể kiểm thử luồng thay đổi state độc lập với giao diện không?
8. Chi phí store/action/effect có xứng đáng với độ phức tạp thực tế không?

Nếu ứng dụng chủ yếu là form và trang nội dung, MVC server-rendered thường là điểm bắt đầu hợp lý. Nếu giao diện có nhiều state tương tác và nhiều thành phần cần phản ứng đồng bộ, UDF có thể làm luồng cập nhật dễ hiểu hơn. Với ứng dụng lớn, dùng MVC ở backend và UDF ở frontend thường là lựa chọn tự nhiên.

## 16. Checklist thiết kế và kiểm thử

### Với MVC

- Controller nhận request và điều phối use case.
- Quy tắc nghiệp vụ nằm trong domain/application layer phù hợp.
- View chỉ trình bày dữ liệu được cung cấp.
- View Model/DTO giới hạn dữ liệu công khai.
- Authentication, authorization và validation được kiểm tra ở server.
- Side effect và transaction có ranh giới rõ.
- Controller, use case, View và persistence có test phù hợp.

### Với UDF

- State có nguồn sở hữu rõ ràng.
- View phát action thay vì sửa shared state tùy tiện.
- Reducer/update tạo state mới và có tính xác định.
- Side effect nằm trong effect hoặc middleware.
- Async response có cơ chế xử lý stale request và lỗi.
- State cục bộ không bị đưa vào global store không cần thiết.
- Reducer, effect và component được kiểm thử riêng.

### Với kiến trúc kết hợp

- Backend vẫn là nguồn có thẩm quyền cho nghiệp vụ.
- API contract có request, response và error semantics rõ.
- Client xử lý optimistic state và rollback khi server từ chối.
- Không tin ID, role, price hoặc tenant do client tự khai báo.
- Client state được đồng bộ sau conflict hoặc response mới.
- Log/trace có thể liên kết action phía client với request phía server mà không ghi dữ liệu nhạy cảm.

## Kết luận

MVC và luồng dữ liệu một chiều giải quyết hai khía cạnh bổ sung. MVC chia trách nhiệm giữa Model, View và Controller; UDF quy định một chu trình cập nhật state từ action đến state mới rồi render View. MVC server-side thường phù hợp với request–response, form và trang nội dung. UDF hữu ích khi giao diện có nhiều trạng thái tương tác, cập nhật bất đồng bộ hoặc cần theo dõi lịch sử thay đổi state.

Hai cách tiếp cận có thể cùng tồn tại. Một frontend dùng UDF có thể gọi backend Spring MVC; backend tiếp tục xác thực, phân quyền, thực hiện use case và lưu dữ liệu có thẩm quyền. Khi mỗi phía giữ đúng trách nhiệm, giao diện có thể phản hồi tốt mà quy tắc nghiệp vụ vẫn được bảo vệ và kiểm thử rõ ràng.
