# Vai trò tương ứng trong Rails, Django và ASP.NET Core MVC

MVC là cách phân chia trách nhiệm giữa tiếp nhận tương tác, xử lý dữ liệu/nghiệp vụ và trình bày kết quả. Các framework web hiện đại hiện thực ý tưởng này bằng thuật ngữ, quy ước và cơ chế khác nhau. Vì vậy, khi chuyển từ một nền tảng sang nền tảng khác, cần đối chiếu **vai trò thực tế** thay vì chỉ tìm những class có tên Model, View hoặc Controller.

Ruby on Rails và ASP.NET Core MVC sử dụng tên MVC khá trực tiếp. Django thường gọi kiến trúc của mình là MTV (Model–Template–View): Django View xử lý request và tạo response, nên về vai trò nó gần với Controller trong MVC; Template của Django mới là phần tương ứng với View. ASP.NET Core MVC có Controller và Razor View rõ ràng, nhưng từ Model được dùng rộng cho nhiều loại dữ liệu như domain model, input model và view model.

Trong module **MODEL_VIEW_CONTROLLER**, người học cần theo dõi luồng request, thiết kế hợp đồng dữ liệu, xử lý biểu mẫu, lỗi, bảo mật và kiểm thử ứng dụng web. So sánh ba nền tảng giúp nhận ra các trách nhiệm kiến trúc có thể giữ nguyên dù tên gọi và cách viết mã thay đổi.

## 1. Bản đồ vai trò giữa ba nền tảng

| Vai trò trong MVC | Ruby on Rails | Django | ASP.NET Core MVC |
|---|---|---|---|
| Tiếp nhận request và điều phối | Controller kế thừa `ApplicationController` hoặc `ActionController::Base` | View function hoặc class-based view | Controller kế thừa `Controller` hoặc `ControllerBase` |
| Phần trình bày | ERB/Haml template, partial, layout | Django Template, include, base template | Razor View `.cshtml`, partial, layout |
| Model nghiệp vụ/dữ liệu | Thường là Active Record model hoặc PORO | Django Model/ORM và các object nghiệp vụ | Domain model/entity, application model |
| Ánh xạ dữ liệu form/request | `params`, Strong Parameters | Request data, Form/ModelForm | Model Binding, Input Model |
| Kiểm tra đầu vào | Active Model validations, custom validation | Form validation, validators, model/database constraints | Data Annotations, custom validation, ModelState |
| Truy cập dữ liệu phổ biến | Active Record | Django ORM | EF Core, DbContext |
| Định tuyến | `config/routes.rb` | URLconf (`urls.py`) | Endpoint/conventional/attribute routing |
| Hợp đồng dữ liệu cho View/API | Instance variables, presenter/serializer/DTO theo nhu cầu | Context dictionary, form, serializer/DTO theo nhu cầu | ViewModel, action result, DTO |
| Xử lý lỗi | Rescue/exception handling, `rescue_from`, error pages | Exception middleware, handlers, HTTP responses | Exception middleware, filters, Problem Details |

Bảng trên mô tả cách tổ chức phổ biến, không phải quy tắc bắt buộc cho mọi dự án. Rails cho phép dùng service object hoặc domain object riêng; Django không bắt buộc mọi nghiệp vụ nằm trong Model; ASP.NET Core MVC không yêu cầu phải dùng EF Core hoặc Repository pattern.

## 2. Rails: MVC theo convention

**Ruby on Rails** tổ chức ứng dụng web theo MVC và sử dụng convention để liên kết route, controller action, model và view. Với một resource như Task, Rails thường đặt các file liên quan trong những thư mục có tên quen thuộc:

~~~text
app/
  controllers/
    tasks_controller.rb
  models/
    task.rb
  views/
    tasks/
      index.html.erb
      show.html.erb
      new.html.erb
      _form.html.erb
config/
  routes.rb
~~~

Convention giúp framework suy ra view tương ứng với controller action. Ví dụ action `TasksController#index` thường render template `app/views/tasks/index.html.erb` nếu không chỉ định template khác hoặc redirect.

### 2.1. Route ánh xạ URL đến Controller action

Trong `config/routes.rb`:

~~~ruby
Rails.application.routes.draw do
  resources :tasks, only: [:index, :show, :new, :create]
end
~~~

Rails tạo các route theo resource:

| HTTP method | Path | Controller action | Ý nghĩa |
|---|---|---|---|
| GET | `/tasks` | `index` | Danh sách công việc |
| GET | `/tasks/:id` | `show` | Chi tiết công việc |
| GET | `/tasks/new` | `new` | Hiển thị form |
| POST | `/tasks` | `create` | Tạo công việc |

Route chịu trách nhiệm nhận diện endpoint và chuyển request đến action. Nó không phải Model, View hoặc một nơi thích hợp để chứa quy tắc nghiệp vụ phức tạp.

### 2.2. Controller tiếp nhận request và chọn response

~~~ruby
class TasksController < ApplicationController
  def index
    @tasks = current_user.tasks.order(created_at: :desc)
  end

  def new
    @task = Task.new
  end

  def create
    @task = current_user.tasks.new(task_params)

    if @task.save
      redirect_to task_path(@task), notice: "Đã tạo công việc."
    else
      render :new, status: :unprocessable_entity
    end
  end

  private

  def task_params
    params.require(:task).permit(:title, :due_date)
  end
end
~~~

Controller:
- Nhận dữ liệu từ request qua `params`.
- Dùng Strong Parameters để chỉ cho phép các trường được chấp nhận.
- Gọi Model hoặc service để thực hiện thao tác.
- Chọn render template hoặc redirect.
- Trả status code phù hợp.

`current_user` trong ví dụ là phương thức do ứng dụng cung cấp, thường đến từ cơ chế xác thực. Việc tạo task thông qua `current_user.tasks` giới hạn owner theo người dùng hiện tại; không lấy owner ID tùy ý từ form rồi tin đó là danh tính hợp lệ.

Controller nên giữ mỏng. Khi use case gồm nhiều bước, tích hợp dịch vụ ngoài hoặc có quy tắc phức tạp, có thể chuyển điều phối sang service object hoặc lớp ứng dụng.

### 2.3. Model thường dùng Active Record

~~~ruby
class Task < ApplicationRecord
  belongs_to :user

  validates :title, presence: true, length: { maximum: 120 }

  enum status: {
    open: 0,
    in_progress: 1,
    done: 2
  }

  def complete!
    raise "Only open tasks can be completed" unless open?

    update!(status: :done)
  end
end
~~~

Active Record kết hợp mapping dữ liệu với hành vi của object. Model có thể khai báo association, validation, scope và phương thức nghiệp vụ.

Rails convention thường đặt nhiều trách nhiệm persistence và validation trong Active Record model. Khi domain phức tạp hơn, có thể tách domain object, policy hoặc service để tránh model trở thành “fat model”. Cần chọn ranh giới dựa trên độ phức tạp thực tế; không phải mọi phương thức đều cần một service class riêng.

Database constraint vẫn cần thiết cho các bất biến như unique hoặc foreign key. Validation của Rails cải thiện phản hồi cho người dùng nhưng không thay thế constraint khi nhiều request ghi đồng thời.

### 2.4. View dùng ERB và partial

`app/views/tasks/index.html.erb`:

~~~erb
<h1>Danh sách công việc</h1>

<% if @tasks.empty? %>
  <p>Chưa có công việc.</p>
<% else %>
  <ul>
    <% @tasks.each do |task| %>
      <li>
        <%= link_to task.title, task_path(task) %>
        <span><%= task.status.humanize %></span>
      </li>
    <% end %>
  </ul>
<% end %>
~~~

ERB cho phép nhúng Ruby vào template. Dùng partial như `_form.html.erb` để tái sử dụng form giữa trang tạo mới và chỉnh sửa. View nên tập trung vào markup và trình bày; không nên gọi nhiều truy vấn hoặc chứa quy tắc chuyển trạng thái nghiệp vụ.

Rails tự động escape nội dung thông thường khi render ERB bằng cú pháp an toàn. Không dùng `raw` hoặc `html_safe` với nội dung không đáng tin cậy nếu chưa xử lý đúng ngữ cảnh.

### 2.5. Form, validation và lỗi

Form thường gửi dữ liệu đến controller. Strong Parameters kiểm soát mass assignment; Active Record validations kiểm tra dữ liệu trước khi lưu. Khi `save` thất bại, controller render lại form và View có thể đọc `@task.errors` để hiển thị lỗi.

Strong Parameters không phải authorization. Cho phép trường `:status` không có nghĩa người dùng được quyền tự chuyển trạng thái. Các thao tác nhạy cảm cần policy/use case kiểm tra quyền và trạng thái hiện tại.

Rails hỗ trợ CSRF protection cho các form web thông qua authenticity token. Endpoint thay đổi dữ liệu cần dùng HTTP method phù hợp và giữ cơ chế bảo vệ CSRF theo cấu hình ứng dụng.

## 3. Django: MTV và vị trí tương đương Controller

Django thường gọi kiến trúc của mình là **Model–Template–View (MTV)**. Tên “View” trong Django có nghĩa là thành phần nhận request, thực hiện xử lý và trả response. Vì thế, khi so sánh với MVC truyền thống:

- Django Model tương ứng với Model.
- Django Template tương ứng với View.
- Django View function/class đảm nhiệm vai trò gần với Controller.

Đây là khác biệt thuật ngữ quan trọng. Không nên kết luận Django thiếu Controller chỉ vì framework gọi request handler là View.

Cấu trúc ứng dụng có thể như sau:

~~~text
project/
  config/
    urls.py
  tasks/
    models.py
    views.py
    urls.py
    forms.py
    templates/
      tasks/
        task_list.html
        task_form.html
~~~

### 3.1. URLconf ánh xạ URL đến Django View

`tasks/urls.py`:

~~~python
from django.urls import path
from . import views

app_name = "tasks"

urlpatterns = [
    path("", views.task_list, name="list"),
    path("new/", views.task_create, name="create"),
]
~~~

Project URLconf có thể include URLconf của app:

~~~python
from django.urls import include, path

urlpatterns = [
    path("tasks/", include("tasks.urls")),
]
~~~

URLconf ánh xạ path và tham số đến view function hoặc class-based view. Nó tương đương vai trò routing trong Rails và ASP.NET Core.

### 3.2. Django View function xử lý request

~~~python
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Task

@login_required
def task_list(request):
    tasks = (
        Task.objects
        .filter(owner=request.user)
        .order_by("-created_at")
    )

    return render(
        request,
        "tasks/task_list.html",
        {"tasks": tasks},
    )
~~~

Hàm `task_list` nhận `HttpRequest`, truy vấn dữ liệu và trả về `HttpResponse` thông qua `render`. Về trách nhiệm, đây là điểm tương đương Controller action trong MVC.

Django có class-based views như ListView hoặc CreateView để đóng gói các luồng phổ biến. Dùng function-based hay class-based view tùy độ phức tạp và nhu cầu mở rộng; cả hai đều là cơ chế xử lý request.

### 3.3. Django Model và ORM

~~~python
from django.conf import settings
from django.db import models

class Task(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Đang mở"
        IN_PROGRESS = "in_progress", "Đang thực hiện"
        DONE = "done", "Hoàn tất"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    title = models.CharField(max_length=120)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    created_at = models.DateTimeField(auto_now_add=True)
~~~

Django Model khai báo trường, quan hệ và metadata của dữ liệu; ORM cung cấp QuerySet để truy vấn. Model method hoặc manager có thể chứa hành vi liên quan, nhưng use case nhiều bước có thể được đặt trong service/application module riêng.

Một chi tiết cần nhớ: gọi `Model.save()` không tự động gọi `full_clean()` trong mọi trường hợp. Nếu muốn chạy model validation, cần gọi rõ hoặc dùng Form/ModelForm và các cơ chế phù hợp. Database constraints vẫn là lớp bảo vệ cuối cho tính duy nhất, khóa ngoại và các bất biến được biểu diễn ở schema.

### 3.4. Template là phần tương ứng với View

`tasks/templates/tasks/task_list.html`:

~~~django
<h1>Danh sách công việc</h1>

{% if tasks %}
  <ul>
    {% for task in tasks %}
      <li>
        {{ task.title }}
        <span>{{ task.get_status_display }}</span>
      </li>
    {% endfor %}
  </ul>
{% else %}
  <p>Chưa có công việc.</p>
{% endif %}
~~~

Django Template dùng cú pháp riêng để hiển thị biến, lặp và điều kiện. Template nên tập trung trình bày; không nên đặt truy vấn database hoặc logic nghiệp vụ vào template tag tùy tiện.

Autoescape được bật mặc định cho nhiều template context tiêu chuẩn. Không dùng `safe` với nội dung do người dùng kiểm soát nếu chưa bảo đảm đã sanitize đúng.

### 3.5. Form và ModelForm

Django có hệ thống Form để binding và validate dữ liệu. ModelForm có thể tạo form từ một Django Model:

~~~python
from django import forms
from .models import Task

class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title"]
~~~

View xử lý GET và POST:

~~~python
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

@login_required
def task_create(request):
    if request.method == "POST":
        form = TaskForm(request.POST)

        if form.is_valid():
            task = form.save(commit=False)
            task.owner = request.user
            task.save()
            return redirect("tasks:list")
    else:
        form = TaskForm()

    return render(
        request,
        "tasks/task_form.html",
        {"form": form},
    )
~~~

Form đảm nhiệm binding và validation; View function điều phối request và quyết định response. `owner` được gán từ `request.user`, không lấy từ input do client tự gửi.

Django có CSRF middleware và template tag `{% csrf_token %}` cho form POST trong ứng dụng web. Với quyền truy cập, có thể dùng decorator, mixin, permission hoặc policy riêng. Việc đăng nhập thành công không tự động có nghĩa người dùng được xem mọi object; queryset vẫn phải được giới hạn theo owner/tenant hoặc quyền phù hợp.

## 4. ASP.NET Core MVC: Controller, Razor View và nhiều loại Model

ASP.NET Core MVC sử dụng tên MVC trực tiếp. Controller xử lý request và trả về Action Result; Razor View render HTML; Model là thuật ngữ rộng chỉ dữ liệu mà action nhận hoặc gửi đến View.

Một cấu trúc phổ biến:

~~~text
Controllers/
  TasksController.cs
Models/
  Task.cs
  CreateTaskInputModel.cs
  TaskListViewModel.cs
Views/
  Tasks/
    Index.cshtml
    Create.cshtml
    _TaskForm.cshtml
Data/
  AppDbContext.cs
~~~

Dự án lớn có thể tổ chức theo feature và tách Application/Domain/Infrastructure. MVC framework không bắt buộc mọi loại Model phải nằm trong một thư mục tên Models.

### 4.1. Routing và Controller action

Trong cấu hình ứng dụng:

~~~csharp
var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllersWithViews();

var app = builder.Build();

app.UseRouting();
// Đăng ký authentication scheme phù hợp trong service container.
app.UseAuthentication();
app.UseAuthorization();

app.MapControllerRoute(
    name: "default",
    pattern: "{controller=Home}/{action=Index}/{id?}");

app.Run();
~~~

Conventional routing ánh xạ URL theo controller/action. ASP.NET Core cũng hỗ trợ attribute routing bằng `[Route]`, `[HttpGet]`, `[HttpPost]` và các attribute tương ứng.

Thứ tự middleware xác thực và phân quyền cần được cấu hình đúng. Route chỉ chọn endpoint; authorization policy vẫn phải được áp dụng ở server.

### 4.2. Input Model và Model Binding

ASP.NET Core Model Binding chuyển dữ liệu từ route, query string và form vào tham số action; request body thường được đọc qua input formatter khi nguồn như `[FromBody]` được chỉ định hoặc được suy luận theo cấu hình API. Nên tạo Input Model mô tả chính xác các trường mà client được phép gửi:

~~~csharp
using System.ComponentModel.DataAnnotations;

public sealed class CreateTaskInputModel
{
    [Required]
    [StringLength(120)]
    public string Title { get; set; } = "";
}
~~~

Không bind trực tiếp toàn bộ domain entity nếu client chỉ được phép sửa một vài trường. Input Model giúp giảm nguy cơ overposting, trong đó client gửi thêm thuộc tính nhạy cảm như OwnerId, Status hoặc IsAdmin.

### 4.3. Controller gọi application service

~~~csharp
[Authorize]
public sealed class TasksController : Controller
{
    private readonly ITaskService _tasks;
    private readonly ICurrentUser _currentUser;

    public TasksController(
        ITaskService tasks,
        ICurrentUser currentUser)
    {
        _tasks = tasks;
        _currentUser = currentUser;
    }

    [HttpGet]
    public async Task<IActionResult> Index(
        CancellationToken cancellationToken)
    {
        var result = await _tasks.GetList(
            _currentUser.UserId,
            cancellationToken);

        var rows = result
            .Select(task => new TaskRowViewModel(
                task.Id,
                task.Title,
                task.StatusLabel))
            .ToList();

        var model = new TaskListViewModel(
            rows,
            rows.Count == 0);
        return View(model);
    }

    [HttpPost]
    [ValidateAntiForgeryToken]
    public async Task<IActionResult> Create(
        CreateTaskInputModel input,
        CancellationToken cancellationToken)
    {
        if (!ModelState.IsValid)
        {
            return View(input);
        }

        await _tasks.Create(
            input.Title,
            _currentUser.UserId,
            cancellationToken);

        return RedirectToAction(nameof(Index));
    }
}
~~~

`ICurrentUser` trong ví dụ là abstraction do ứng dụng định nghĩa để lấy danh tính đã xác thực; đây không phải kiểu có sẵn bắt buộc của ASP.NET Core. Giả sử `ITaskService.GetList` trả về một collection có các thuộc tính `Id`, `Title` và `StatusLabel`; Controller ánh xạ chúng thành các hàng của ViewModel. `ITaskService` đại diện cho application service. Controller không tự viết SQL và không quyết định các quy tắc chuyển trạng thái.

### 4.4. ViewModel và Razor View

ASP.NET Core thường phân biệt:
- Domain entity: mô hình nghiệp vụ.
- Input Model: dữ liệu nhận từ form/request.
- ViewModel: dữ liệu đã chuẩn bị cho Razor View.
- DTO: hợp đồng trao đổi giữa các tầng hoặc API.

Ví dụ ViewModel:

~~~csharp
public sealed record TaskRowViewModel(
    Guid Id,
    string Title,
    string StatusLabel);
    
public sealed record TaskListViewModel(
    IReadOnlyList<TaskRowViewModel> Tasks,
    bool IsEmpty);
~~~

Razor View `Views/Tasks/Index.cshtml`:

~~~cshtml
@model TaskListViewModel

<h1>Danh sách công việc</h1>

@if (Model.IsEmpty)
{
    <p>Chưa có công việc.</p>
}
else
{
    <ul>
    @foreach (var task in Model.Tasks)
    {
        <li>
            @task.Title
            <span>@task.StatusLabel</span>
        </li>
    }
    </ul>
}
~~~

Razor thực hiện HTML encoding cho biểu thức thông thường. Cần thận trọng với `Html.Raw` vì nó bỏ qua encoding; không render HTML không đáng tin cậy như nội dung an toàn.

### 4.5. Validation và ModelState

Data Annotations như `[Required]` và `[StringLength]` được sử dụng bởi Model Validation. Sau model binding và validation, Controller kiểm tra `ModelState.IsValid`. Nếu không hợp lệ, action có thể trả lại View cùng Input Model để người dùng sửa.

`[ValidateAntiForgeryToken]` bảo vệ action POST bằng antiforgery token. `[Authorize]` yêu cầu request đã xác thực theo policy tương ứng. Cả hai giải quyết những vấn đề khác nhau: antiforgery chống request giả mạo từ trình duyệt; authorization kiểm tra quyền thực hiện hành động.

EF Core thường được dùng để truy cập dữ liệu qua `DbContext`, nhưng ASP.NET Core MVC không bắt buộc EF Core hoặc một Repository abstraction cụ thể. Với ứng dụng nhiều use case, application service và data access abstraction giúp tách HTTP khỏi persistence.

## 5. So sánh luồng xử lý cùng một use case

Xét use case tạo công việc có tiêu đề bắt buộc và gắn owner theo người dùng đã đăng nhập:

~~~mermaid
flowchart TD
    A["Người dùng gửi POST /tasks"] --> B["Routing chọn request handler"]
    B --> C{"Nền tảng"}
    C --> R["Rails: TasksController#create"]
    C --> D["Django: task_create view"]
    C --> N["ASP.NET: TasksController.Create"]
    R --> V["Bind + validate + authorize"]
    D --> V
    N --> V
    V --> S["Application / Model operation"]
    S --> P["Persistence"]
    P --> O["Redirect hoặc response"]
    O --> H["View render kết quả"]
~~~

| Bước | Rails | Django | ASP.NET Core MVC |
|---|---|---|---|
| Chọn handler | Rails router | URLconf | Endpoint routing |
| Đọc input | `params` | `request.POST` và Form | Model Binding |
| Kiểm tra input | Strong Parameters + Active Model validation | Form/ModelForm validation | Model Validation + ModelState |
| Gán danh tính | Current user từ authentication layer | `request.user` | Claims/principal qua abstraction |
| Thực hiện use case | Model/service object | View gọi Model/service | Controller gọi application service |
| Lưu dữ liệu phổ biến | Active Record | Django ORM | EF Core/DbContext |
| Phản hồi thành công | Redirect/render | Redirect/render | RedirectToAction/View/ActionResult |
| Phản hồi validation | Render lại template với errors | Render template với form errors | Trả View với ModelState |

Tên phương thức và vị trí file khác nhau, nhưng các câu hỏi thiết kế vẫn giống nhau: ai được phép gửi trường nào, ai xác minh quyền, quy tắc nghiệp vụ nằm ở đâu, transaction bao quanh thao tác nào và View nhận dữ liệu gì?

## 6. Đối chiếu form binding và validation

Form là nơi khác biệt giữa các framework thể hiện rõ:

| Khía cạnh | Rails | Django | ASP.NET Core MVC |
|---|---|---|---|
| Dữ liệu request | `params` | `request.POST` / `request.GET` | Model Binding |
| Object form | Thường dùng Model hoặc Form Object | Form / ModelForm | Input Model / ViewModel |
| Allow fields | Strong Parameters | Khai báo `fields` trong Form/ModelForm | Chọn thuộc tính trong Input Model |
| Validation | Active Model validations | Field/Form/Model validation theo cách gọi | Data Annotations/custom validation |
| Kết quả lỗi | `errors` trên object | `form.errors` | `ModelState` |
| Render lại | `render :new` hoặc template | `render(request, template, context)` | `return View(input)` |

Điểm chung: lỗi đầu vào cần được chuyển về đúng form và giữ lại dữ liệu người dùng có thể sửa. Điểm khác: framework cung cấp object, lifecycle và API validation riêng.

Không được nhầm validation đầu vào với quy tắc nghiệp vụ. Ví dụ title có độ dài hợp lệ chưa chắc người dùng có quyền tạo task trong dự án cụ thể. Application service vẫn phải kiểm tra quyền và domain model vẫn bảo vệ trạng thái.

## 7. Đối chiếu Model và lớp truy cập dữ liệu

Các framework đều cung cấp ORM phổ biến, nhưng mức độ kết hợp giữa Model và persistence khác nhau:

| Nền tảng | Cơ chế phổ biến | Ghi chú kiến trúc |
|---|---|---|
| Rails | Active Record | Model thường gắn trực tiếp với bảng và có validation/association |
| Django | Django ORM | Model khai báo schema/quan hệ; query qua Manager/QuerySet |
| ASP.NET Core | EF Core | Entity và DbContext; có thể dùng repository hoặc truy vấn qua application service |

ORM không tự động tạo ra kiến trúc domain tốt. Một entity có thể chỉ là cấu trúc persistence; domain behavior có thể nằm trong entity, domain service hoặc application layer tùy cách tổ chức.

Khi nghiệp vụ phức tạp:
- Giữ quy tắc nghiệp vụ độc lập với HTTP.
- Xác định transaction theo use case.
- Đưa truy vấn vào nơi có thể kiểm soát tenant/owner.
- Dùng DTO/ViewModel để không trả nguyên entity ra giao diện.
- Dùng database constraint cho các bất biến cần bảo vệ đồng thời.

Rails Active Record model thường tích hợp persistence và validation. Django Model cũng mô tả schema và có thể chứa method/manager. EF Core có thể ánh xạ domain entity hoặc persistence entity riêng. Không cần ép ba nền tảng vào cùng một cấu trúc class; cần giữ cùng nguyên tắc về trách nhiệm.

## 8. Bảo mật: những trách nhiệm tương đương

Tên API khác nhau, nhưng các yêu cầu bảo mật cơ bản giống nhau:

| Mục tiêu | Rails | Django | ASP.NET Core MVC |
|---|---|---|---|
| Xác thực | Authentication framework/gem hoặc cơ chế ứng dụng | Authentication middleware, `request.user` | Authentication middleware, ClaimsPrincipal |
| Phân quyền | Policy/authorization logic trong ứng dụng | Permissions, decorators, mixins hoặc policy | `[Authorize]`, policy/authorization service |
| Chống CSRF cho form | Authenticity token | CSRF middleware và `{% csrf_token %}` | Antiforgery token và `[ValidateAntiForgeryToken]` |
| Chống mass assignment/overposting | Strong Parameters | Form khai báo field được phép | Input Model giới hạn thuộc tính |
| XSS | ERB auto-escaping mặc định theo ngữ cảnh thông thường | Template autoescape mặc định | Razor HTML encoding |
| Giới hạn dữ liệu | Scope/query theo current user và policy | QuerySet theo owner/tenant | Query theo user/tenant và authorization |

Một số điểm cần kiểm tra ở mọi nền tảng:

1. Không tin owner ID, role hoặc tenant ID do client tự gửi.
2. Kiểm tra quyền trên tài nguyên cụ thể, không chỉ kiểm tra đã đăng nhập.
3. Giới hạn query theo owner/tenant để tránh truy cập chéo dữ liệu.
4. Dùng parameter binding/ORM query API, tránh nối chuỗi SQL.
5. Dùng output encoding và không đánh dấu HTML không đáng tin là safe.
6. Dùng CSRF protection cho cookie-authenticated browser requests có thay đổi trạng thái.
7. Không trả exception, SQL hoặc stack trace nội bộ cho người dùng.

Ẩn một nút trong View không phải authorization. Client vẫn có thể gọi endpoint trực tiếp. Server phải xác minh quyền ở mỗi use case.

## 9. Xử lý lỗi và phản hồi HTTP

Cả ba nền tảng đều có thể render HTML, redirect hoặc trả JSON, nhưng cơ chế được đặt ở những nơi khác nhau.

- **Rails:** controller có thể render template hoặc redirect; exception có thể được xử lý cục bộ, bằng `rescue_from` hoặc error handling ở tầng ứng dụng.
- **Django:** view trả HttpResponse/redirect; exception middleware và error handlers xử lý lỗi theo phạm vi request.
- **ASP.NET Core MVC:** controller trả IActionResult; exception middleware, exception filters hoặc Problem Details có thể chuẩn hóa lỗi.

Lỗi validation thường cần render lại form. Lỗi không tìm thấy có thể trả 404. Lỗi xung đột nghiệp vụ có thể trả 409 cho API hoặc một trang thông báo cho HTML. Lỗi không dự kiến cần response an toàn và log nội bộ.

Không nên chuyển mọi exception thành 200 hoặc hiển thị message nội bộ. Hợp đồng HTTP cần nhất quán giữa các endpoint.

## 10. Kiểm thử theo nền tảng

| Loại test | Rails | Django | ASP.NET Core |
|---|---|---|---|
| Unit test Model/service | Minitest hoặc RSpec | Django TestCase/Python test tools | xUnit/NUnit/MSTest |
| Controller/request test | Controller/Integration tests | Test Client với URL/view | Controller unit test hoặc MVC integration |
| Integration test | Rails integration/system tests | TestCase, TransactionTestCase | WebApplicationFactory/TestServer |
| Kiểm thử database | Test database, transactional fixtures | Test database và transaction test | Test database, EF Core provider/container |
| Kiểm thử giao diện | System tests với browser driver | Browser/E2E tools | Browser/E2E tools |

Tên framework test không quan trọng bằng phạm vi test:

- Model/domain test xác minh quy tắc nghiệp vụ.
- Request/Controller test xác minh routing, binding, status và response.
- Repository integration test xác minh truy vấn và constraint trên database phù hợp.
- Security test xác minh người dùng không truy cập tài nguyên ngoài quyền.
- Browser test xác minh form và luồng tương tác quan trọng.

Khi test transaction hoặc locking, nên dùng database engine tương thích production. SQLite, in-memory provider hoặc mock có thể không tái hiện đầy đủ behavior của database production. Đặc biệt với EF Core, InMemory provider không phải relational database; nó không chứng minh SQL translation, foreign key hoặc transaction semantics giống hệ quản trị thật.

## 11. Những điểm có thể chuyển giao khi đổi nền tảng

Khi chuyển từ Rails sang Django hoặc ASP.NET Core MVC, hãy giữ lại tư duy phân chia trách nhiệm:

- Controller-equivalent nhận request và chọn response.
- View/Template/Razor chỉ trình bày dữ liệu đã chuẩn bị.
- Model/domain giữ trạng thái và quy tắc nghiệp vụ.
- Form/input model là hợp đồng đầu vào.
- ViewModel/DTO là hợp đồng đầu ra.
- Repository/ORM chịu trách nhiệm persistence.
- Authentication xác định danh tính; authorization kiểm tra quyền.
- Transaction bao quanh use case cần tính nguyên tử.
- Test được đặt theo ranh giới cần xác minh.

Những gì cần học lại là API và convention cụ thể:
- Rails: routes, controller callbacks, params, Strong Parameters, Active Record, partial và Rails testing.
- Django: URLconf, function/class-based views, Form/ModelForm, QuerySet, middleware và Django testing.
- ASP.NET Core: routing, dependency injection, model binding, ModelState, filters/middleware, Razor và WebApplicationFactory.

Không nên mang nguyên cách đặt tên class hoặc package từ framework này sang framework khác rồi coi đó là tương đương. Hãy xác định trách nhiệm trước, sau đó chọn cơ chế tự nhiên của nền tảng.

## 12. Chọn nền tảng và mức abstraction

Cả ba framework đều hỗ trợ xây dựng ứng dụng MVC server-rendered. Chọn framework phụ thuộc vào ngôn ngữ, hệ sinh thái, kỹ năng đội ngũ, tích hợp cần thiết, vận hành và yêu cầu sản phẩm.

| Tiêu chí | Rails | Django | ASP.NET Core MVC |
|---|---|---|---|
| Ngôn ngữ | Ruby | Python | C# |
| Phong cách | Convention mạnh, nhiều chức năng tích hợp | Framework đầy đủ, tách app và URLconf rõ | Tích hợp sâu với .NET, DI và middleware |
| ORM phổ biến | Active Record | Django ORM | EF Core |
| Template | ERB và các lựa chọn khác | Django Template | Razor |
| Điểm mạnh về quy ước | Resourceful routing, convention over configuration | App, URLconf, Form/ModelForm, admin ecosystem | Strong typing, DI, middleware, model binding |
| Trade-off cần chú ý | Active Record có thể gom nhiều trách nhiệm vào model | View function/class có thể phình nếu thiếu application boundary | Cần thiết kế rõ Input Model, ViewModel và service boundary |

Không framework nào tự động bảo đảm kiến trúc tốt. Convention có thể tăng tốc phát triển nhưng vẫn cần kiểm soát dependency, quyền truy cập, transaction và độ phức tạp của model/controller.

### 12.1. Khi nào nên thêm service/presenter layer?

Có thể thêm lớp ứng dụng hoặc presenter khi:
- Một thao tác gồm nhiều bước hoặc nhiều repository.
- Nghiệp vụ được gọi từ web, background job và message handler.
- Cần transaction rõ ràng.
- Logic hiển thị được dùng lại hoặc cần unit test riêng.
- Controller/View function bắt đầu chứa nhiều nhánh nghiệp vụ.
- Domain cần tách khỏi ORM hoặc framework.

Không cần thêm một lớp chỉ để đổi tên phương thức rồi chuyển tiếp lời gọi. Abstraction nên bảo vệ một ranh giới có ý nghĩa.

## 13. Những sai lầm thường gặp khi đối chiếu framework

| Sai lầm | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| Django View chính là View của MVC | Django View nhận request và trả response | Nó gần vai trò Controller; Django Template gần View |
| Rails Model chỉ là database row | Active Record model có association, validation và hành vi | Có thể chứa domain behavior, nhưng cần tránh fat model |
| ASP.NET Core Model chỉ có một class Model | Thuật ngữ Model bao gồm nhiều dạng dữ liệu | Phân biệt entity, input model, view model và DTO |
| ORM tự động giải quyết phân quyền | Query hợp lệ vẫn có thể trả dữ liệu sai owner | Giới hạn query và kiểm tra authorization |
| Form validation thay thế domain validation | Use case có thể được gọi từ nhiều nguồn | Bảo vệ bất biến trong domain/application |
| Strong Parameters/Model Binding là authorization | Chỉ kiểm soát binding trường, không chứng minh quyền | Kiểm tra quyền theo người dùng và tài nguyên |
| View có thể quyết định quyền cuối cùng | Client có thể gọi endpoint trực tiếp | Server xác minh quyền ở use case |
| Mọi dự án phải có Repository pattern | Framework ORM đã cung cấp abstraction persistence | Chỉ thêm repository khi nó tạo ranh giới có ích |
| Test bằng mock chứng minh database đúng | Mock không thực thi SQL hoặc constraint | Dùng integration test với database phù hợp |

## 14. Quy trình đọc một codebase MVC mới

Khi bắt đầu với một framework hoặc dự án chưa quen, có thể đọc theo trình tự:

1. Tìm route/URL mapping để biết request đi vào đâu.
2. Mở controller action hoặc Django view được route gọi.
3. Xác định dữ liệu đầu vào được binding và kiểm tra ở đâu.
4. Theo lời gọi sang application service, model method hoặc use case.
5. Tìm ORM/repository và cách query được giới hạn theo owner/tenant.
6. Xác định template/ViewModel/serializer dùng để tạo response.
7. Kiểm tra error handler, authentication, authorization và CSRF.
8. Tìm test tương ứng với request và persistence.
9. Vẽ lại luồng request bằng tên thành phần thực tế của framework.

Khi đã xác định được luồng, hãy đánh giá xem trách nhiệm có nằm đúng nơi không: Controller có đang chứa nghiệp vụ? Template có truy vấn database? Model có phụ thuộc HTTP? Query có lọc đúng người dùng? Test có kiểm tra database thật khi cần?

## 15. Những điểm cần ghi nhớ

Rails và ASP.NET Core MVC dùng thuật ngữ MVC khá trực tiếp. Django dùng MTV: Django View nhận request và tạo response nên đảm nhiệm vai trò gần với Controller; Django Template là phần tương ứng với View. Đây là khác biệt thuật ngữ quan trọng nhất khi đối chiếu ba nền tảng.

Rails thường dùng Active Record cho Model và convention để nối route/controller/template. Django dùng URLconf, function/class-based view, Model, Form/ModelForm và Template. ASP.NET Core MVC dùng routing, Controller, Model Binding, ModelState, Razor View và thường kết hợp EF Core cho persistence. Mỗi framework có API riêng nhưng đều cần phân tách input contract, nghiệp vụ, lưu trữ và trình bày.

Khi chuyển nền tảng, hãy giữ nguyên các nguyên tắc: Controller-equivalent điều phối HTTP; View chỉ trình bày; Model/domain bảo vệ quy tắc; application service điều phối use case phức tạp; ORM/repository quản lý persistence; server xác minh quyền; transaction và test bảo vệ tính nhất quán dữ liệu. Đối chiếu trách nhiệm trước khi đối chiếu tên class sẽ giúp đọc và thiết kế ứng dụng MVC trên bất kỳ nền tảng nào.
