# Xử lý sự kiện bàn phím, chuột và lựa chọn

Trong MVC tương tác, View không chỉ hiển thị dữ liệu mà còn tiếp nhận hành động của người dùng. Người dùng nhấn phím, nhấp chuột, chọn một mục, thay đổi ô nhập hoặc gửi biểu mẫu. Mỗi hành động có thể phát sinh một sự kiện (event) mà Controller tiếp nhận, diễn giải thành thao tác của ứng dụng và chuyển đến Model. Sau khi trạng thái thay đổi, View hiển thị kết quả mới.

Luồng xử lý này tạo ra ranh giới rõ ràng giữa tương tác và nghiệp vụ: View phát sinh sự kiện, Controller điều phối, Model quản lý trạng thái và quy tắc. Trong ứng dụng web, trình duyệt cung cấp hệ thống sự kiện DOM cho bàn phím, chuột, con trỏ, biểu mẫu và lựa chọn. Nếu dùng đúng các sự kiện và điều khiển HTML có ngữ nghĩa, ứng dụng sẽ dễ dùng bằng chuột, bàn phím, thiết bị cảm ứng và công nghệ hỗ trợ.

Bài học thuộc module **MODEL_VIEW_CONTROLLER**, nơi người học theo dõi luồng request, thiết kế hợp đồng dữ liệu, xử lý biểu mẫu, lỗi, bảo mật và kiểm thử MVC trong ứng dụng web. Nội dung tập trung vào cách sự kiện từ giao diện trở thành hành động của Controller và cập nhật trạng thái hiển thị.

## 1. Sự kiện đi qua MVC như thế nào?

Sự kiện là thông báo rằng một điều gì đó đã xảy ra: người dùng nhấn nút, thay đổi giá trị, nhấn phím, chọn một tùy chọn hoặc gửi biểu mẫu. Trong trình duyệt, đối tượng Event chứa thông tin về sự kiện và phần tử phát sinh sự kiện.

Một luồng MVC tương tác thường gồm các bước:

1. Người dùng thực hiện hành động trên View.
2. Trình duyệt phát sinh sự kiện DOM.
3. Listener trong Controller nhận sự kiện.
4. Controller đọc dữ liệu cần thiết, kiểm tra ngữ cảnh giao diện và chuyển thành lệnh hoặc thao tác.
5. Model thay đổi trạng thái hoặc thực hiện quy tắc ứng dụng.
6. View đọc trạng thái mới và cập nhật phần hiển thị.

~~~mermaid
flowchart TD
    U["Người dùng nhấn phím, nhấp chuột hoặc chọn mục"] --> V["View / DOM phát sinh event"]
    V --> C["Controller nhận và diễn giải event"]
    C --> M["Model xử lý command và quy tắc"]
    M --> S["Trạng thái ứng dụng thay đổi"]
    S --> R["View render lại dữ liệu"]
    R --> U2["Người dùng nhìn thấy kết quả"]
~~~

Ví dụ, người dùng đánh dấu một công việc là hoàn thành. Checkbox trong View phát sinh sự kiện change. Controller đọc mã công việc và trạng thái checkbox, sau đó yêu cầu Model cập nhật trạng thái. View hiển thị công việc đã hoàn thành.

Trong MVC phía máy chủ, thao tác có thể tiếp tục tạo HTTP request gửi đến Controller trên server. Controller phía server gọi dịch vụ ứng dụng và Model, sau đó trả HTML hoặc JSON. Vì vậy, một ứng dụng web có thể có hai ranh giới tương tác: Controller phía trình duyệt xử lý phản hồi tức thời của giao diện, và Controller phía server xử lý request HTTP. Không nên nhầm sự kiện DOM với sự kiện nghiệp vụ được lưu hoặc phát tán trong hệ thống.

### 1.1. Event, handler và listener

- **Event** là đối tượng mô tả sự kiện vừa xảy ra.
- **Event listener** là hàm được đăng ký để nhận một loại sự kiện trên một phần tử.
- **Event handler** là phần mã xử lý sự kiện; trong thực tế hai thuật ngữ listener và handler đôi khi được dùng thay thế nhau.
- **Event target** là phần tử nơi sự kiện bắt đầu.
- **Current target** là phần tử mà listener đang được đăng ký và hiện được gọi.

Có thể đăng ký listener bằng addEventListener:

~~~javascript
const saveButton = document.querySelector("#save-button");

saveButton.addEventListener("click", (event) => {
    console.log("Người dùng đã kích hoạt nút lưu");
});
~~~

Cách này tách phần xử lý khỏi cấu trúc HTML và cho phép đăng ký nhiều listener. Khi không cần listener nữa, có thể gỡ bằng removeEventListener với cùng tham chiếu hàm và cùng tùy chọn tương ứng.

Nên đăng ký listener sau khi phần tử DOM đã tồn tại, chẳng hạn dùng script có thuộc tính defer hoặc đợi DOMContentLoaded. Nếu querySelector trả về null mà gọi addEventListener ngay, ứng dụng sẽ phát sinh lỗi.

## 2. Vòng đời và lan truyền sự kiện DOM

Sự kiện DOM có thể đi qua ba giai đoạn:

1. **Capturing:** sự kiện đi từ document xuống các phần tử con trên đường đến phần tử đích.
2. **Target:** sự kiện đến phần tử phát sinh.
3. **Bubbling:** sự kiện lan ngược từ phần tử đích lên các phần tử cha, nếu loại sự kiện hỗ trợ bubbling.

~~~mermaid
flowchart TD
    A["document"] --> B["main"]
    B --> C["form"]
    C --> D["button: event target"]
    D --> C2["form: bubbling"]
    C2 --> B2["main: bubbling"]
    B2 --> A2["document: bubbling"]
~~~

Mặc định, addEventListener đăng ký listener ở giai đoạn bubbling. Có thể truyền tùy chọn capture để nhận sự kiện ở giai đoạn capturing:

~~~javascript
document.addEventListener("click", handleClick, { capture: true });
~~~

### 2.1. Phân biệt preventDefault và stopPropagation

Hai phương thức thường bị nhầm:

- **preventDefault()** ngăn hành vi mặc định của trình duyệt, nếu sự kiện có hành vi mặc định và không bị passive listener giới hạn.
- **stopPropagation()** ngăn sự kiện tiếp tục lan truyền qua các phần tử khác.

Ví dụ, khi xử lý submit bằng JavaScript và không muốn trình duyệt tải lại trang, có thể gọi preventDefault(). Điều này không tự ngăn listener khác nhận sự kiện.

Không nên gọi stopPropagation() theo thói quen. Việc chặn bubbling có thể làm mất hành vi của thành phần cha, event delegation hoặc thư viện giao diện. Chỉ dừng lan truyền khi hợp đồng tương tác thực sự yêu cầu điều đó.

### 2.2. Event delegation

Thay vì đăng ký listener cho từng phần tử con, có thể đăng ký một listener trên phần tử cha và dựa vào bubbling để xác định phần tử được tương tác. Cách này gọi là event delegation.

~~~javascript
const taskList = document.querySelector("#task-list");

taskList.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");

    if (!button || !taskList.contains(button)) {
        return;
    }

    if (button.dataset.action === "delete") {
        taskController.deleteTask(button.dataset.taskId);
    }
});
~~~

Event delegation hữu ích khi danh sách được render động hoặc có nhiều nút tương tự. Khi một phần tử mới được thêm vào danh sách, listener ở phần tử cha vẫn nhận được sự kiện mà không cần đăng ký lại.

Không phải sự kiện nào cũng bubbling. Với những sự kiện không bubbling, cần chọn listener phù hợp, dùng capture khi cần hoặc xử lý trực tiếp trên phần tử đích. Cần kiểm tra đặc tính của loại event thay vì giả định tất cả đều lan truyền giống click.

## 3. Xử lý sự kiện bàn phím

Sự kiện bàn phím giúp người dùng nhập dữ liệu, kích hoạt điều khiển, di chuyển giữa các vùng và sử dụng phím tắt. Một số sự kiện thường gặp:

| Sự kiện | Ý nghĩa | Tình huống sử dụng |
|---|---|---|
| keydown | Phím bắt đầu được nhấn | Phím tắt, điều khiển trò chơi, điều hướng tùy chỉnh |
| keyup | Phím được thả ra | Kết thúc thao tác giữ phím |
| input | Giá trị của ô nhập thay đổi | Tìm kiếm trực tiếp, kiểm tra dữ liệu khi nhập |
| beforeinput | Trình duyệt sắp thay đổi nội dung nhập | Ứng dụng soạn thảo cần kiểm soát thao tác chỉnh sửa |
| compositionstart / compositionend | Bắt đầu/kết thúc nhập liệu qua bộ gõ IME | Xử lý tiếng Việt, tiếng Nhật, tiếng Trung |

Sự kiện keypress đã lỗi thời (deprecated); ứng dụng mới nên dùng keydown, keyup và các sự kiện input phù hợp.

### 3.1. key và code khác nhau

Đối tượng KeyboardEvent cung cấp hai thuộc tính quan trọng:

- **key** mô tả ký tự hoặc ý nghĩa của phím theo bố cục bàn phím và trạng thái modifier. Ví dụ: Enter, Escape, ArrowDown hoặc một ký tự.
- **code** mô tả vị trí phím vật lý trên bàn phím, ví dụ KeyW hoặc Space.

Đối với phím tắt theo ký tự người dùng nhìn thấy, thường dùng key. Đối với điều khiển phụ thuộc vị trí vật lý như trò chơi, code có thể phù hợp hơn.

~~~javascript
document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
        closeDialog();
    }

    if (event.key === "ArrowDown") {
        moveSelectionDown();
    }
});
~~~

Khi xử lý phím tắt, cần xét các modifier như ctrlKey, shiftKey, altKey và metaKey. Trên macOS, metaKey thường tương ứng với phím Command; trên nhiều hệ điều hành khác, ctrlKey được dùng phổ biến.

### 3.2. Không chặn các phím nhập liệu thông thường

Một listener toàn cục có thể vô tình chiếm phím mà người dùng đang cần nhập vào input, textarea hoặc vùng contenteditable. Trước khi xử lý phím tắt, hãy kiểm tra phần tử đang có focus và loại trừ trường hợp nhập liệu.

~~~javascript
document.addEventListener("keydown", (event) => {
    if (event.isComposing || event.repeat) {
        return;
    }

    const target = event.target;
    const isEditing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        target.isContentEditable;

    if (isEditing) {
        return;
    }

    if ((event.ctrlKey || event.metaKey) &&
        event.key.toLowerCase() === "k") {
        event.preventDefault();
        document.querySelector("#search-input").focus();
    }
});
~~~

Đây là ví dụ về phím tắt mở ô tìm kiếm. Chỉ triển khai phím tắt khi nó có ích và không xung đột với thao tác quen thuộc của trình duyệt hoặc công nghệ hỗ trợ.

### 3.3. Tôn trọng nhập liệu bằng IME

Người dùng gõ tiếng Việt có thể sử dụng bộ gõ xử lý nhiều phím trung gian trước khi tạo thành ký tự cuối cùng. Trong thời gian composition, các sự kiện keydown và input có thể xuất hiện theo chuỗi mà không đại diện cho một ký tự đã hoàn tất.

Khi xử lý phím tắt, nên kiểm tra event.isComposing để không hiểu nhầm thao tác của bộ gõ là lệnh ứng dụng. Với ô tìm kiếm, sự kiện input thường phù hợp để cập nhật kết quả sau mỗi thay đổi; nếu cần đợi người dùng hoàn tất một cụm ký tự, có thể phối hợp compositionend.

### 3.4. Ưu tiên hành vi bàn phím có sẵn của HTML

Các phần tử button, input, select, textarea và liên kết đã có hành vi bàn phím theo chuẩn trình duyệt. Người dùng có thể Tab để di chuyển focus, Enter để kích hoạt liên kết hoặc nút, Space để kích hoạt button và thay đổi checkbox, dùng phím mũi tên để di chuyển trong một số điều khiển lựa chọn.

Nếu tạo một phần tử div rồi gắn click listener để giả lập nút, ứng dụng phải tự bổ sung tabindex, role, focus style và xử lý phím Enter/Space. Dùng button thật thường đơn giản và dễ tiếp cận hơn.

Không nên tự bắt các phím Tab, Enter hoặc Space trên toàn trang nếu không có lý do rõ ràng. Việc ghi đè hành vi mặc định có thể phá vỡ điều hướng bằng bàn phím.

## 4. Xử lý sự kiện chuột và con trỏ

Chuột thường tạo ra các sự kiện click, dblclick, mousedown, mouseup, mousemove, mouseenter, mouseleave và contextmenu. Những sự kiện này phục vụ tương tác trỏ và kéo thả.

| Sự kiện | Ý nghĩa | Ví dụ |
|---|---|---|
| click | Người dùng kích hoạt một phần tử | Mở chi tiết, gửi lệnh |
| dblclick | Kích hoạt hai lần liên tiếp | Mở chế độ chỉnh sửa đặc biệt |
| mousedown / mouseup | Nút chuột được nhấn hoặc thả | Bắt đầu/kết thúc thao tác kéo |
| mousemove | Con trỏ di chuyển | Theo dõi vùng vẽ hoặc kéo |
| mouseenter / mouseleave | Con trỏ đi vào/rời phần tử | Hiển thị gợi ý phụ |
| contextmenu | Người dùng mở menu ngữ cảnh | Menu thao tác riêng của ứng dụng |

### 4.1. Dùng click cho thao tác kích hoạt

Với nút hành động, nên dùng sự kiện click trên button. Trình duyệt sẽ kích hoạt nút bằng chuột, bàn phím và nhiều phương thức nhập khác. Không nên chỉ dùng mousedown vì người dùng có thể nhấn xuống rồi kéo ra ngoài trước khi thả; hành vi đó khác với một lần click hoàn chỉnh.

~~~html
<button type="button" id="refresh-button">
    Làm mới danh sách
</button>
~~~

~~~javascript
document.querySelector("#refresh-button")
    .addEventListener("click", () => {
        taskController.refresh();
    });
~~~

### 4.2. Pointer Events cho chuột, bút và cảm ứng

Pointer Events cung cấp một mô hình thống nhất cho chuột, bút cảm ứng và thiết bị cảm ứng. Những sự kiện thường dùng gồm pointerdown, pointerup, pointermove, pointercancel, pointerenter và pointerleave.

Nếu xây dựng thao tác kéo thả hoặc vẽ, Pointer Events thường phù hợp hơn việc viết riêng các nhánh mouse và touch. Thuộc tính pointerType cho biết nguồn tương tác là mouse, pen hay touch.

~~~javascript
const drawingArea = document.querySelector("#drawing-area");

drawingArea.addEventListener("pointerdown", (event) => {
    drawingArea.setPointerCapture(event.pointerId);
    beginDrawing(event.clientX, event.clientY);
});

drawingArea.addEventListener("pointermove", (event) => {
    if (event.buttons === 0) {
        return;
    }

    continueDrawing(event.clientX, event.clientY);
});

drawingArea.addEventListener("pointerup", (event) => {
    finishDrawing();
    drawingArea.releasePointerCapture(event.pointerId);
});

drawingArea.addEventListener("pointercancel", () => {
    cancelDrawing();
});
~~~

Ví dụ chỉ minh họa vòng đời tương tác. Ứng dụng vẽ thực tế cần quản lý trạng thái đang kéo, pointerId, nhiều điểm chạm, hủy thao tác và giới hạn vùng vẽ. Pointer capture giúp phần tử tiếp tục nhận sự kiện con trỏ ngay cả khi con trỏ đi ra ngoài biên của nó.

### 4.3. Không phụ thuộc vào hover

Hover thường không tồn tại hoặc không thuận tiện trên màn hình cảm ứng. Không nên giấu chức năng quan trọng sau mouseenter hoặc yêu cầu người dùng rê chuột để xem hướng dẫn thiết yếu. Hãy cung cấp một cách kích hoạt thay thế bằng click, bàn phím hoặc điều khiển rõ ràng.

Nếu dùng hover để hiển thị tooltip, tooltip nên có thể truy cập bằng focus bàn phím và không che khuất nội dung cần đọc. Đối với thao tác kéo thả, nên cân nhắc thêm nút di chuyển lên/xuống hoặc cách sắp xếp bằng bàn phím.

## 5. Xử lý lựa chọn và thay đổi biểu mẫu

Lựa chọn là tương tác phổ biến trong ứng dụng web: chọn một tùy chọn, đánh dấu checkbox, chọn radio, chọn nhiều mục hoặc bôi đen văn bản. Những điều khiển HTML phù hợp giúp trình duyệt cung cấp hành vi chuẩn và thông tin ngữ nghĩa.

### 5.1. Phân biệt input và change

- Sự kiện **input** thường phát sinh mỗi khi giá trị của điều khiển nhập thay đổi, phù hợp với tìm kiếm trực tiếp hoặc xem trước.
- Sự kiện **change** phát sinh khi thay đổi được xác nhận theo quy tắc của loại điều khiển. Với select và checkbox, nó thường xảy ra ngay sau khi lựa chọn thay đổi; với text input, thường xảy ra khi giá trị được commit, chẳng hạn khi rời focus.

Ví dụ cập nhật bộ lọc khi người dùng chọn trạng thái:

~~~html
<label for="task-filter">Trạng thái</label>
<select id="task-filter" name="status">
    <option value="all">Tất cả</option>
    <option value="open">Chưa hoàn thành</option>
    <option value="done">Đã hoàn thành</option>
</select>
~~~

~~~javascript
const filter = document.querySelector("#task-filter");

filter.addEventListener("change", (event) => {
    taskController.setFilter(event.target.value);
});
~~~

Với ô tìm kiếm, có thể dùng input để cập nhật kết quả theo từng thay đổi:

~~~javascript
const searchInput = document.querySelector("#search-input");

searchInput.addEventListener("input", (event) => {
    taskController.search(event.target.value);
});
~~~

Khi tìm kiếm trên dữ liệu lớn hoặc gọi API, nên debounce thao tác để tránh gửi request sau mỗi ký tự. Dù có debounce, server vẫn cần kiểm tra và giới hạn truy vấn.

### 5.2. Checkbox và radio có ngữ nghĩa khác nhau

Checkbox biểu diễn một lựa chọn độc lập có thể bật hoặc tắt. Nhiều checkbox có thể cùng được chọn. Radio biểu diễn lựa chọn loại trừ lẫn nhau trong cùng một nhóm.

~~~html
<fieldset>
    <legend>Các loại thông báo</legend>

    <label>
        <input type="checkbox" name="notifications" value="email">
        Email
    </label>

    <label>
        <input type="checkbox" name="notifications" value="push">
        Thông báo đẩy
    </label>
</fieldset>

<fieldset>
    <legend>Mức ưu tiên</legend>

    <label>
        <input type="radio" name="priority" value="normal" checked>
        Bình thường
    </label>

    <label>
        <input type="radio" name="priority" value="high">
        Cao
    </label>
</fieldset>
~~~

Khi đọc trạng thái, dùng thuộc tính checked của checkbox hoặc radio. Không dựa vào thuộc tính value để suy ra trạng thái bật/tắt; value là giá trị được gửi khi điều khiển được chọn.

~~~javascript
const notificationInputs =
    document.querySelectorAll('input[name="notifications"]');

notificationInputs.forEach((input) => {
    input.addEventListener("change", () => {
        const selected = Array.from(notificationInputs)
            .filter((item) => item.checked)
            .map((item) => item.value);

        settingsController.setNotificationChannels(selected);
    });
});
~~~

Với radio, có thể đọc phần tử đang checked trong nhóm. Không cần tự viết lại hành vi chọn một mục duy nhất mà trình duyệt đã cung cấp.

### 5.3. Select một lựa chọn và nhiều lựa chọn

Với select một lựa chọn, có thể đọc select.value. Với select multiple, đọc selectedOptions để lấy tất cả tùy chọn đang được chọn:

~~~javascript
const categorySelect = document.querySelector("#categories");

categorySelect.addEventListener("change", () => {
    const selectedValues = Array.from(categorySelect.selectedOptions)
        .map((option) => option.value);

    taskController.setCategories(selectedValues);
});
~~~

Không nên giả định selectedIndex luôn là một giá trị hợp lệ. Người dùng có thể bỏ lựa chọn hoặc điều khiển có trạng thái rỗng tùy cấu hình. Cần xác định rõ giá trị mặc định, trường hợp không chọn và quy tắc nhiều lựa chọn trong hợp đồng dữ liệu.

### 5.4. Lựa chọn văn bản

Đối với một số tính năng như đánh dấu đoạn văn, trích dẫn hoặc tìm kiếm trong nội dung, có thể cần biết vùng văn bản được chọn. Sự kiện select áp dụng cho một số ô nhập văn bản; sự kiện selectionchange trên document theo dõi thay đổi vùng chọn của tài liệu.

~~~javascript
document.addEventListener("selectionchange", () => {
    const selection = document.getSelection();
    const selectedText = selection ? selection.toString() : "";

    if (selectedText.trim().length > 0) {
        selectionController.preview(selectedText);
    }
});
~~~

Không nên gửi nội dung được chọn lên server hoặc ghi log chỉ vì người dùng bôi đen văn bản. Chỉ xử lý khi tính năng thực sự cần và phải tôn trọng quyền riêng tư cũng như ngữ cảnh nội dung.

## 6. Đưa sự kiện vào Controller, không để View tự quyết định nghiệp vụ

Listener nên chuyển dữ liệu sự kiện thành thao tác có ý nghĩa. Ví dụ, listener có thể lấy taskId và checked từ checkbox, rồi gọi taskController.setCompleted(taskId, checked). Model mới là nơi quyết định trạng thái có thể thay đổi hay không.

Không nên đưa toàn bộ đối tượng DOM Event vào Model. Event chứa chi tiết giao diện như target, key, button và vị trí con trỏ; Model không cần biết những chi tiết đó. Controller nên trích xuất dữ liệu cần thiết và chuyển thành command hoặc tham số đơn giản.

Một cách phân chia dễ đọc:

- View: HTML và hàm render trạng thái.
- Controller: listener, diễn giải thao tác, điều phối và thông báo kết quả.
- Model: dữ liệu, quy tắc và thao tác thay đổi trạng thái.

Nếu dùng framework frontend, tên gọi và cách triển khai có thể khác nhau, nhưng ranh giới trách nhiệm vẫn hữu ích. Không nên tạo một lớp Controller lớn chứa mọi listener và mọi hành vi của toàn ứng dụng; có thể nhóm controller theo màn hình hoặc use case có liên quan.

## 7. Ví dụ hoàn chỉnh: danh sách công việc tương tác

Ví dụ dưới đây tạo danh sách công việc đơn giản. Người dùng có thể thêm công việc bằng biểu mẫu, đánh dấu hoàn thành bằng checkbox và lọc danh sách bằng select. HTML dùng điều khiển có ngữ nghĩa; Controller nhận sự kiện; Model giữ trạng thái; View render dữ liệu.

### 7.1. View bằng HTML

~~~html
<form id="task-form">
    <label for="task-title">Tên công việc</label>
    <input id="task-title" name="title"
           required maxlength="120">
    <button type="submit">Thêm công việc</button>
</form>

<label for="task-filter">Lọc công việc</label>
<select id="task-filter">
    <option value="all">Tất cả</option>
    <option value="open">Chưa hoàn thành</option>
    <option value="done">Đã hoàn thành</option>
</select>

<ul id="task-list" aria-label="Danh sách công việc"></ul>
<p id="task-status" role="status" aria-live="polite"></p>
~~~

Label liên kết với input bằng for và id. Nút submit có thể được kích hoạt bằng bàn phím. Checkbox tạo ra trong danh sách cũng có thể được thao tác bằng Space. Vùng role=status thông báo kết quả cập nhật cho công nghệ hỗ trợ.

### 7.2. Model giữ trạng thái và quy tắc

~~~javascript
const taskModel = {
    tasks: [],
    filter: "all",

    add(title) {
        const task = {
            id: crypto.randomUUID(),
            title: title,
            completed: false
        };

        this.tasks.push(task);
        return task;
    },

    setCompleted(id, completed) {
        const task = this.tasks.find((item) => item.id === id);

        if (!task) {
            return null;
        }

        task.completed = completed;
        return task;
    },

    setFilter(filter) {
        const allowed = ["all", "open", "done"];

        if (!allowed.includes(filter)) {
            return false;
        }

        this.filter = filter;
        return true;
    },

    visibleTasks() {
        if (this.filter === "open") {
            return this.tasks.filter((task) => !task.completed);
        }

        if (this.filter === "done") {
            return this.tasks.filter((task) => task.completed);
        }

        return this.tasks;
    }
};
~~~

Model không biết DOM, listener hay loại thiết bị nhập. Nó nhận dữ liệu đơn giản và thay đổi trạng thái theo thao tác được yêu cầu. Trong ứng dụng thực tế, quy tắc có thể phức tạp hơn và dữ liệu cần được lưu qua API hoặc cơ sở dữ liệu.

### 7.3. View render trạng thái

~~~javascript
const taskList = document.querySelector("#task-list");
const statusMessage = document.querySelector("#task-status");

const taskView = {
    render() {
        const tasks = taskModel.visibleTasks();
        taskList.replaceChildren();

        tasks.forEach((task) => {
            const item = document.createElement("li");
            item.dataset.taskId = task.id;

            const label = document.createElement("label");
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.checked = task.completed;
            checkbox.dataset.action = "toggle";
            checkbox.dataset.taskId = task.id;

            const title = document.createElement("span");
            title.textContent = task.title;

            label.append(checkbox, title);
            item.append(label);
            taskList.append(item);
        });

        this.announce("Đang hiển thị " + tasks.length + " công việc.");
    },

    updateTask(task) {
        const selector = 'li[data-task-id="' +
            CSS.escape(task.id) + '"]';
        const item = taskList.querySelector(selector);

        if (item) {
            item.classList.toggle("completed", task.completed);
        }
    },

    announce(message) {
        statusMessage.textContent = message;
    }
};
~~~

Dùng textContent để đưa tiêu đề người dùng nhập vào DOM dưới dạng văn bản. Không nối trực tiếp dữ liệu không tin cậy vào innerHTML vì nội dung có thể bị trình duyệt diễn giải thành HTML hoặc script.

### 7.4. Controller tiếp nhận sự kiện

~~~javascript
const taskController = {
    create(rawTitle) {
        const title = rawTitle.trim();

        if (!title) {
            taskView.announce("Vui lòng nhập tên công việc.");
            return false;
        }

        taskModel.add(title);
        taskView.render();
        taskView.announce("Đã thêm công việc.");
        return true;
    },

    toggle(id, completed) {
        const task = taskModel.setCompleted(id, completed);

        if (!task) {
            taskView.announce("Không tìm thấy công việc.");
            return;
        }

        taskView.updateTask(task);
        taskView.announce(
            completed ? "Đã hoàn thành công việc." : "Đã mở lại công việc."
        );
    },

    setFilter(filter) {
        if (!taskModel.setFilter(filter)) {
            return;
        }

        taskView.render();
    }
};

const taskForm = document.querySelector("#task-form");
const titleInput = document.querySelector("#task-title");
const filterSelect = document.querySelector("#task-filter");

taskForm.addEventListener("submit", (event) => {
    event.preventDefault();

    if (taskController.create(titleInput.value)) {
        taskForm.reset();
        titleInput.focus();
    }
});

taskList.addEventListener("change", (event) => {
    const target = event.target;

    if (!(target instanceof HTMLInputElement)) {
        return;
    }

    if (target.dataset.action !== "toggle") {
        return;
    }

    taskController.toggle(target.dataset.taskId, target.checked);
});

filterSelect.addEventListener("change", (event) => {
    taskController.setFilter(event.target.value);
});

taskView.render();
~~~

Ví dụ dùng event delegation trên taskList để nhận change của các checkbox được tạo động. Khi checkbox thay đổi, Controller trích xuất taskId và checked rồi gọi Model. Khi lọc, Controller cập nhật filter trong Model và yêu cầu View render lại.

Khi đánh dấu hoàn thành, View chỉ cập nhật class của dòng tương ứng thay vì render lại toàn danh sách. Cách này giữ focus trên checkbox mà người dùng vừa thao tác. Khi render lại toàn bộ danh sách, cần chú ý bảo toàn focus và vị trí bàn phím để người dùng không bị mất điểm tương tác.

Ví dụ chỉ lưu trạng thái trong bộ nhớ trình duyệt. Nếu cần dữ liệu tồn tại sau khi tải lại trang hoặc được chia sẻ giữa nhiều người dùng, Controller phía trình duyệt phải gửi request đến server. Server cần xác thực, kiểm tra quyền, xác thực dữ liệu và thực hiện quy tắc nghiệp vụ; trạng thái phía trình duyệt không phải nguồn dữ liệu đáng tin cậy.

## 8. Từ sự kiện giao diện đến request trên server

Với ứng dụng web có lưu dữ liệu, một hành động có thể phát sinh request bất đồng bộ. Ví dụ, người dùng đánh dấu công việc hoàn thành; Controller phía trình duyệt gửi lệnh đến endpoint; Controller phía server gọi use case và trả kết quả.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant View as View / Browser
    participant Client as Client Controller
    participant Server as Server Controller
    participant Model as Model / Use Case
    User->>View: Chọn checkbox
    View->>Client: change event
    Client->>Server: PATCH /tasks/{id}
    Server->>Model: setCompleted(id, true)
    Model-->>Server: Kết quả nghiệp vụ
    Server-->>Client: HTTP response
    Client->>View: Cập nhật trạng thái hiển thị
~~~

Ví dụ gửi request:

~~~javascript
async function updateTaskOnServer(taskId, completed) {
    const response = await fetch(
        "/api/tasks/" + encodeURIComponent(taskId),
        {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ completed: completed })
        }
    );

    if (!response.ok) {
        throw new Error("Không thể cập nhật công việc.");
    }

    return response.json();
}
~~~

Đoạn mã minh họa request JSON; ứng dụng thực tế cần bổ sung cơ chế xác thực và CSRF phù hợp với cấu hình triển khai. Không tin dữ liệu client chỉ vì nó đến từ giao diện đã render. Server phải kiểm tra ID, quyền sở hữu, trạng thái hiện tại và kiểu dữ liệu.

Với request bất đồng bộ, cần quyết định cách giao diện phản ứng khi request thất bại. Có thể giữ trạng thái cũ đến khi server xác nhận, hoặc cập nhật lạc quan rồi rollback nếu server từ chối. Nếu nhiều request cùng sửa một tài nguyên, cần xử lý phản hồi đến sai thứ tự và xung đột phiên bản.

Không nên gửi request cho mọi sự kiện pointermove hoặc keydown nếu thao tác không yêu cầu. Hãy gom thay đổi, debounce hoặc throttle khi phù hợp, và gửi command có ý nghĩa thay vì truyền toàn bộ chuỗi sự kiện thô lên server.

## 9. Khả năng truy cập: mọi thao tác cần dùng được bằng bàn phím

Ứng dụng tương tác phải hoạt động với nhiều phương thức nhập. Một chức năng chỉ có thể thực hiện bằng chuột sẽ gây khó khăn cho người dùng bàn phím, người dùng thiết bị hỗ trợ và một số thiết bị cảm ứng.

Các nguyên tắc quan trọng:

- Dùng button cho hành động, a cho điều hướng, input cho nhập liệu, select cho lựa chọn.
- Gắn label với điều khiển bằng for/id hoặc lồng điều khiển bên trong label.
- Đảm bảo thứ tự Tab hợp lý và focus luôn nhìn thấy được.
- Không dùng màu sắc làm tín hiệu duy nhất cho trạng thái.
- Cung cấp thông báo trạng thái phù hợp, chẳng hạn role=status hoặc aria-live.
- Không tự ý bắt và chặn phím Tab, Enter, Space hay Escape nếu không có hành vi thay thế tương đương.
- Nếu tạo widget tùy chỉnh như menu, combobox hoặc listbox, cần thực hiện đầy đủ quy tắc bàn phím và ARIA phù hợp.
- Với thao tác kéo thả, cung cấp phương thức thay thế bằng bàn phím hoặc nút điều khiển.

Ví dụ, một nút tùy chỉnh được tạo từ div phải tự xử lý role, tabindex và phím kích hoạt. Dùng button thật giúp trình duyệt cung cấp sẵn phần lớn hành vi đó:

~~~html
<button type="button" id="delete-task">
    Xóa công việc
</button>
~~~

Nếu cần hộp thoại, khi mở cần chuyển focus vào vùng phù hợp; khi đóng cần đưa focus về phần tử đã mở nó. Với menu và combobox, không nên tự tạo phím mũi tên điều hướng nếu chưa xác định rõ mô hình tương tác và trạng thái focus.

## 10. Quản lý focus và trạng thái sau tương tác

Focus cho biết phần tử nào đang nhận bàn phím. Sau một thao tác, vị trí focus có thể ảnh hưởng trực tiếp đến khả năng tiếp tục sử dụng ứng dụng.

Một số quy tắc hữu ích:

- Sau khi gửi biểu mẫu và render lại, giữ focus ở trường phù hợp hoặc chuyển đến thông báo kết quả nếu luồng yêu cầu.
- Khi xóa một phần tử đang được focus, chuyển focus đến phần tử hợp lý tiếp theo.
- Khi mở dialog, chuyển focus vào dialog và giữ điều hướng trong dialog theo đúng hành vi modal.
- Khi đóng dialog, trả focus về điều khiển đã mở dialog.
- Khi render danh sách, tránh thay toàn bộ DOM nếu điều đó làm mất focus, vị trí đọc hoặc trạng thái nhập.
- Khi cập nhật nội dung bất đồng bộ, thông báo kết quả mà không tự ý chuyển focus nếu không cần thiết.

Có thể kiểm tra phần tử đang focus qua document.activeElement. Tuy nhiên, không nên dùng focus như một cách thay thế cho thông báo trạng thái. Người dùng công nghệ hỗ trợ cần được thông báo có ý nghĩa khi kết quả thay đổi.

## 11. An toàn khi xử lý sự kiện và dữ liệu đầu vào

Sự kiện đến từ trình duyệt không bảo đảm dữ liệu là hợp lệ hoặc đáng tin cậy. Người dùng có thể thay đổi DOM, sửa request, gọi endpoint trực tiếp hoặc gửi một giá trị không xuất hiện trong danh sách lựa chọn.

Một số nguyên tắc:

1. **Kiểm tra lại ở server.** Validation phía trình duyệt giúp trải nghiệm tốt hơn, nhưng không thay thế validation và quy tắc nghiệp vụ ở server.
2. **Không tin thuộc tính data-* hoặc hidden input.** Chúng chỉ là dữ liệu client có thể sửa. ID, quyền, giá và trạng thái phải được kiểm tra ở server.
3. **Dùng textContent cho văn bản.** Tránh đưa chuỗi không tin cậy vào innerHTML hoặc API thực thi HTML nếu không sanitize đúng cách.
4. **Mã hóa URL và dữ liệu request.** Dùng URL encoding phù hợp và JSON serialization thay vì tự nối chuỗi dữ liệu vào request.
5. **Bảo vệ request thay đổi trạng thái.** Dùng xác thực, phân quyền và CSRF protection phù hợp với cơ chế cookie/session.
6. **Giới hạn tần suất và kích thước.** Sự kiện lặp nhanh hoặc request liên tục có thể gây tải lớn; server cần giới hạn phù hợp.
7. **Không ghi log dữ liệu nhạy cảm không cần thiết.** Nội dung được chọn, dữ liệu nhập và thông tin định danh cần được xử lý theo mục đích rõ ràng.

## 12. Kiểm thử tương tác

Kiểm thử sự kiện cần xác minh cả phản ứng của View lẫn hành vi của Model và Controller. Một listener được gọi chưa đủ chứng minh tính năng hoạt động đúng.

Có thể chia kiểm thử theo các phạm vi:

| Phạm vi | Điều cần xác minh |
|---|---|
| View | Phần tử có ngữ nghĩa, label, trạng thái hiển thị, thông báo và focus |
| Controller | Event được diễn giải đúng, dữ liệu được trích xuất đúng, hành động phù hợp được gọi |
| Model | Quy tắc thay đổi trạng thái, lựa chọn hợp lệ và dữ liệu không hợp lệ |
| Tích hợp | Request, response, xác thực, phân quyền và cập nhật giao diện sau khi server trả kết quả |
| Khả năng truy cập | Điều hướng bằng Tab, kích hoạt bằng Enter/Space, thông báo cho công nghệ hỗ trợ |

Các kịch bản nên kiểm thử:

- Nhấn Enter trong biểu mẫu gửi đúng thao tác một lần.
- Checkbox thay đổi bằng chuột và bằng Space đều cập nhật cùng trạng thái.
- Select thay đổi bằng chuột hoặc phím mũi tên đều áp dụng đúng bộ lọc.
- Phím tắt không can thiệp khi người dùng đang nhập bằng IME.
- Click vào phần tử con bên trong nút vẫn được xử lý đúng qua event delegation.
- Request thất bại thì giao diện hiển thị lỗi và trạng thái không bị sai lệch.
- Người dùng không có quyền không thể thực hiện thao tác bằng cách gọi endpoint trực tiếp.
- Khi danh sách được render lại, focus không bị mất một cách bất ngờ.

Nên kết hợp unit test cho Model và Controller với kiểm thử component hoặc browser test cho tương tác thực tế. Một số hành vi focus, pointer và bàn phím chỉ được xác minh đầy đủ khi chạy trong trình duyệt.

## 13. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Gắn mọi listener ở document | Controller khó quản lý và nhiều sự kiện không liên quan bị xử lý | Đăng ký ở phần tử hoặc vùng giao diện phù hợp |
| Dùng div giả làm button | Thiếu hành vi bàn phím và ngữ nghĩa | Dùng button hoặc điều khiển HTML chuẩn |
| Chỉ hỗ trợ mouseover | Người dùng cảm ứng và bàn phím không tiếp cận được chức năng | Cung cấp click/focus hoặc điều khiển thay thế |
| Gọi stopPropagation không cần thiết | Listener ở thành phần cha không nhận được event | Chỉ chặn bubbling khi có yêu cầu rõ |
| Đưa Event DOM vào Model | Model phụ thuộc trình duyệt và giao diện | Controller trích xuất dữ liệu và tạo command |
| Coi dữ liệu client là đáng tin | Có thể sửa quyền, ID hoặc trạng thái bằng request giả | Xác minh dữ liệu và quyền ở server |
| Render lại toàn bộ DOM sau mọi thao tác | Mất focus, trạng thái nhập và hiệu năng | Cập nhật phần cần thiết hoặc khôi phục focus |
| Gửi request cho mọi sự kiện chuyển động | Tạo tải lớn và phản hồi không ổn định | Debounce, throttle hoặc gom thao tác |

## 14. Quy trình thiết kế một tương tác MVC

Khi thêm một tương tác mới, có thể đi theo các bước:

1. Xác định hành động người dùng và kết quả mong muốn.
2. Chọn điều khiển HTML có ngữ nghĩa phù hợp với hành động.
3. Chọn loại event phù hợp: click, keydown, input, change, submit hoặc pointer event.
4. Xác định listener thuộc phạm vi View nào và có thể dùng event delegation không.
5. Trích xuất dữ liệu cần thiết từ event trong Controller.
6. Chuyển thành lệnh rõ ràng và yêu cầu Model thực hiện quy tắc.
7. Cập nhật View từ trạng thái mới; quản lý focus và thông báo.
8. Nếu cần lưu trên server, gửi request và xử lý lỗi, trạng thái chờ, kết quả bất đồng bộ.
9. Kiểm thử chuột, bàn phím, lựa chọn, khả năng truy cập và trường hợp request thất bại.

Không phải tương tác nào cũng cần một listener riêng. Dùng HTML chuẩn và hành vi mặc định của trình duyệt khi có thể. Chỉ viết xử lý tùy chỉnh khi ứng dụng cần một hành vi riêng mà điều khiển tiêu chuẩn không đáp ứng.

## 15. Những điểm cần ghi nhớ

Sự kiện bàn phím, chuột và lựa chọn là đầu vào của View trong MVC tương tác. Controller tiếp nhận event, trích xuất thông tin cần thiết và chuyển thành hành động có ý nghĩa. Model quản lý trạng thái và quy tắc; View hiển thị kết quả mới.

Hãy chọn đúng loại event, hiểu vòng đời và bubbling, ưu tiên điều khiển HTML có ngữ nghĩa, hỗ trợ bàn phím và công nghệ hỗ trợ, giữ dữ liệu DOM tách khỏi Model và xác minh mọi dữ liệu quan trọng ở server. Với tương tác bất đồng bộ, cần quản lý lỗi, focus và trạng thái khi request thất bại.

Một luồng tương tác tốt giúp người dùng thực hiện cùng một hành động bằng phương thức nhập phù hợp, giúp Controller dễ theo dõi và giữ quy tắc nghiệp vụ nhất quán dù thao tác đến từ giao diện nào.
